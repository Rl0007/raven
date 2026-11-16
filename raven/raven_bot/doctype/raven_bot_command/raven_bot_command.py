# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

COMMAND_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,32}$")


class RavenBotCommand(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from raven.raven_bot.doctype.raven_bot_command_channel.raven_bot_command_channel import (
			RavenBotCommandChannel,
		)

		bot: DF.Link
		channels: DF.TableMultiSelect[RavenBotCommandChannel]
		command: DF.Data
		description: DF.Data
		enabled: DF.Check
		handler: DF.Data | None
		server_script: DF.Link | None
		usage_hint: DF.Data | None
	# end: auto-generated types

	def before_naming(self):
		self.command = (self.command or "").strip().lstrip("/").lower()

	def validate(self):
		self.validate_command_name()
		self.validate_handler()

	def validate_command_name(self):
		if not COMMAND_NAME_PATTERN.match(self.command):
			frappe.throw(_("Command can only have lowercase letters, digits and underscores (up to 32)."))

	def validate_handler(self):
		if bool(self.handler) == bool(self.server_script):
			frappe.throw(_("Set either a Handler or a Server Script, not both."))
		if self.server_script:
			self.validate_server_script()
		elif self.handler not in frappe.get_hooks("raven_slash_command_handlers"):
			frappe.throw(
				_("Handler {0} is not listed in any app's raven_slash_command_handlers hook.").format(
					frappe.bold(self.handler)
				)
			)

	def validate_server_script(self):
		if frappe.db.get_value("Server Script", self.server_script, "script_type") != "API":
			frappe.throw(
				_("Server Script {0} must be of type API.").format(frappe.bold(self.server_script))
			)
