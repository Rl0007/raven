import { Extension } from "@tiptap/core"
import { Suggestion } from "@tiptap/suggestion"
import { createSuggestionRender } from "./createSuggestion"
import { slashCommandPluginKey } from "./suggestion"

export interface SlashCommandItem {
    command: string
    description: string
    usage_hint?: string | null
}

interface SlashCommandSuggestionOptions {
    getCommands: () => SlashCommandItem[]
}

export const filterSlashCommands = (commands: SlashCommandItem[], query: string): SlashCommandItem[] => {
    const q = query.toLowerCase()
    const startsWith = commands.filter((item) => item.command.startsWith(q))
    const contains = commands.filter(
        (item) => !item.command.startsWith(q) && `${item.command} ${item.description}`.toLowerCase().includes(q),
    )
    return [...startsWith, ...contains]
}

export const SlashCommandSuggestion = Extension.create<SlashCommandSuggestionOptions>({
    name: "slashCommandSuggestion",

    addOptions() {
        return { getCommands: () => [] }
    },

    addProseMirrorPlugins() {
        return [
            Suggestion<SlashCommandItem, SlashCommandItem>({
                editor: this.editor,
                char: "/",
                pluginKey: slashCommandPluginKey,
                startOfLine: true,
                allow: ({ range }) => range.from <= 1,
                items: ({ query }) => filterSlashCommands(this.options.getCommands(), query),
                command: ({ editor, range, props }) => {
                    editor.chain().focus().insertContentAt(range, `/${props.command} `).run()
                },
                render: createSuggestionRender<SlashCommandItem, SlashCommandItem>({
                    getKey: (item) => item.command,
                    toCommandArg: (item) => item,
                    renderItem: (item) => <SlashCommandRow item={item} />,
                }),
            }),
        ]
    },
})

const SlashCommandRow = ({ item }: { item: SlashCommandItem }) => (
    <span className="flex min-w-0 flex-col">
        <span className="truncate">
            <span className="font-medium">/{item.command}</span>
            {item.usage_hint && <span className="text-ink-gray-5"> {item.usage_hint}</span>}
        </span>
        <span className="truncate text-sm text-ink-gray-5">{item.description}</span>
    </span>
)
