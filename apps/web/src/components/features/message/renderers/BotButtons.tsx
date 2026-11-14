import { useMemo, useState } from "react"
import { useFrappePostCall, type FrappeError } from "frappe-react-sdk"
import type { Message } from "@raven/types/common/Message"
import { Button } from "@components/ui/button"
import { errorResponseToast } from "@components/ui/error-banner"
import { parseRepliedMessageDetails } from "@utils/messageUtils"
import _ from "@lib/translate"

interface BotButton {
    label: string
    value: string
}

export const BotButtons = ({ message }: { message: Message }) => {
    const buttons = useMemo(
        () => parseRepliedMessageDetails<{ buttons?: BotButton[] }>(message.json)?.buttons ?? [],
        [message.json],
    )
    const { call } = useFrappePostCall("raven.raven_bot.slash_commands.press_button")
    const [pressed, setPressed] = useState<string | null>(null)

    if (!message.is_bot_message || buttons.length === 0) return null

    const press = async (value: string) => {
        setPressed(value)
        try {
            await call({ message_id: message.name, value })
        } catch (error) {
            errorResponseToast(_("Could not send your answer"), error as FrappeError)
        } finally {
            setPressed(null)
        }
    }

    return (
        <div className="flex flex-wrap gap-1.5 pt-1">
            {buttons.map((button) => (
                <Button
                    key={button.value}
                    variant="outline"
                    size="sm"
                    disabled={pressed !== null}
                    onClick={() => press(button.value)}
                >
                    {button.label}
                </Button>
            ))}
        </div>
    )
}
