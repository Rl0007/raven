import { useEffect, useRef, type MutableRefObject } from "react"
import { useFrappeGetCall } from "frappe-react-sdk"
import type { SlashCommandItem } from "./slashCommand"

export const useSlashCommands = (channelID: string): MutableRefObject<SlashCommandItem[]> => {
    const { data } = useFrappeGetCall<{ message: SlashCommandItem[] }>(
        "raven.raven_bot.slash_commands.get_slash_commands",
        { channel_id: channelID },
        `slash_commands_${channelID}`,
        { revalidateOnFocus: false },
    )
    const commandsRef = useRef<SlashCommandItem[]>([])
    useEffect(() => {
        commandsRef.current = data?.message ?? []
    }, [data])
    return commandsRef
}
