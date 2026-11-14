import json
import re

import frappe
from frappe import _

SLASH_COMMAND_PATTERN = re.compile(r"^/([a-z0-9_]{1,32})(?:\s+(.*))?$", re.DOTALL)
FLOW_TIMEOUT_SECONDS = 30 * 60


@frappe.whitelist(methods=["GET"])
def get_slash_commands(channel_id: str) -> list[dict]:
	frappe.has_permission("Raven Channel", "read", doc=channel_id, throw=True)
	return [
		{"command": command.name, "description": command.description, "usage_hint": command.usage_hint}
		for command in get_channel_commands(channel_id)
	]


def get_channel_commands(channel_id: str) -> list:
	commands = frappe.get_all(
		"Raven Bot Command",
		filters={"enabled": 1},
		fields=["name", "description", "usage_hint", "bot", "handler"],
		order_by="name asc",
	)
	if not commands:
		return []
	restricted_channels = get_restricted_channels([command.name for command in commands])
	home_channel = get_home_channel(channel_id)
	return [
		command
		for command in commands
		if not restricted_channels.get(command.name) or home_channel in restricted_channels[command.name]
	]


def get_restricted_channels(command_names: list[str]) -> dict[str, set[str]]:
	rows = frappe.get_all(
		"Raven Bot Command Channel",
		filters={"parenttype": "Raven Bot Command", "parent": ("in", command_names)},
		fields=["parent", "channel"],
	)
	restricted_channels = {}
	for row in rows:
		restricted_channels.setdefault(row.parent, set()).add(row.channel)
	return restricted_channels


def get_home_channel(channel_id: str) -> str:
	if frappe.get_cached_value("Raven Channel", channel_id, "is_thread"):
		return frappe.db.get_value("Raven Message", channel_id, "channel_id") or channel_id
	return channel_id


class SlashCommand:
	def __init__(self, message):
		self.message = message
		match = SLASH_COMMAND_PATTERN.match((message.content or "").strip())
		self.name = match.group(1) if match else None
		self.arguments = (match.group(2) or "").strip() if match else ""

	def get_command(self):
		if not self.name:
			return None
		for command in get_channel_commands(self.message.channel_id):
			if command.name == self.name:
				return command
		return None

	def run(self):
		command = self.get_command()
		if not command:
			return
		interaction = SlashCommandInteraction(command, self.message, self.arguments)
		reply = call_handler(command, interaction)
		if reply:
			send_bot_reply(command, self.message, reply)


class SlashCommandInteraction:
	def __init__(self, command, message, arguments, state=None, pressed=None):
		self.command = command
		self.message = message
		self.arguments = arguments
		self.user = message.owner
		self.state = state or {}
		self.pressed = pressed


def call_handler(command, interaction) -> dict | None:
	if command.handler not in frappe.get_hooks("raven_slash_command_handlers"):
		return {"text": _("/{0} is not available right now.").format(command.name)}
	try:
		reply = frappe.get_attr(command.handler)(interaction)
	except frappe.ValidationError as error:
		return {"text": str(error)}
	except Exception:
		frappe.log_error(title=_("Slash command /{0} failed").format(command.name))
		return {"text": _("Something went wrong while running /{0}.").format(command.name)}
	return {"text": reply} if isinstance(reply, str) else reply


def send_bot_reply(command, origin_message, reply: dict):
	bot_message = frappe.get_doc(
		{
			"doctype": "Raven Message",
			"channel_id": origin_message.channel_id,
			"message_type": "Text",
			"is_bot_message": 1,
			"bot": frappe.get_cached_value("Raven Bot", command.bot, "raven_user"),
			"text": markdown_to_html(reply.get("text")),
			"json": get_buttons_json(reply),
		}
	)
	bot_message.insert(ignore_permissions=True)
	save_flow(bot_message.name, command.name, origin_message, reply)


def update_bot_reply(bot_message, reply: dict):
	bot_message.text = markdown_to_html(reply.get("text"))
	bot_message.json = get_buttons_json(reply)
	bot_message.flags.editing_metadata = True
	bot_message.flags.is_bot_step = True
	bot_message.save(ignore_permissions=True)


def markdown_to_html(text: str | None) -> str:
	return frappe.utils.md_to_html(text or "").rstrip("\n")


def get_buttons_json(reply: dict) -> str | None:
	buttons = [
		{"label": str(button["label"]), "value": str(button["value"])}
		for button in reply.get("buttons") or []
	]
	return json.dumps({"buttons": buttons}) if buttons else None


def get_button_values(bot_message) -> list[str]:
	if not bot_message.json:
		return []
	return [button["value"] for button in json.loads(bot_message.json).get("buttons", [])]


def get_flow_cache_key(bot_message_id: str) -> str:
	return f"raven:slash_command_flow:{bot_message_id}"


def save_flow(bot_message_id: str, command_name: str, origin_message, reply: dict):
	if not reply.get("buttons"):
		frappe.cache.delete_value(get_flow_cache_key(bot_message_id))
		return
	flow = {
		"command": command_name,
		"message_id": origin_message.name,
		"user": origin_message.owner,
		"state": reply.get("state") or {},
	}
	frappe.cache.set_value(
		get_flow_cache_key(bot_message_id), flow, expires_in_sec=FLOW_TIMEOUT_SECONDS
	)


@frappe.whitelist(methods=["POST"])
def press_button(message_id: str, value: str):
	flow = frappe.cache.get_value(get_flow_cache_key(message_id))
	if not flow:
		frappe.throw(_("This has expired. Run the command again."))
	if flow["user"] != frappe.session.user:
		frappe.throw(_("Only the person who ran this command can answer it."), frappe.PermissionError)
	bot_message = frappe.get_doc("Raven Message", message_id)
	if value not in get_button_values(bot_message):
		frappe.throw(_("That option is no longer available."))

	command = frappe.get_doc("Raven Bot Command", flow["command"])
	origin_message = frappe.get_doc("Raven Message", flow["message_id"])
	arguments = SlashCommand(origin_message).arguments
	interaction = SlashCommandInteraction(command, origin_message, arguments, flow["state"], value)
	reply = call_handler(command, interaction) or {"text": bot_message.content}
	update_bot_reply(bot_message, reply)
	save_flow(message_id, command.name, origin_message, reply)


def queue_slash_command(message):
	if message.is_bot_message or message.message_type != "Text":
		return
	slash_command = SlashCommand(message)
	if not slash_command.get_command():
		return
	frappe.enqueue(
		run_slash_command,
		message_id=message.name,
		enqueue_after_commit=True,
		at_front=True,
		job_name=f"raven_slash_command::{message.name}",
	)


def run_slash_command(message_id: str):
	SlashCommand(frappe.get_doc("Raven Message", message_id)).run()
