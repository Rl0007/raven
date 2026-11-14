import { describe, expect, it } from "vitest"
import { filterSlashCommands, type SlashCommandItem } from "./slashCommand"

const commands: SlashCommandItem[] = [
    { command: "deploy", description: "Ship a branch" },
    { command: "devbox", description: "Manage dev boxes" },
    { command: "status", description: "Box and deploy status" },
]

const names = (query: string) => filterSlashCommands(commands, query).map((item) => item.command)

describe("filterSlashCommands", () => {
    it("lists every command for a bare slash", () => {
        expect(names("")).toEqual(["deploy", "devbox", "status"])
    })

    it("puts prefix matches before description matches", () => {
        expect(names("dep")).toEqual(["deploy", "status"])
    })

    it("is case-insensitive and drops non-matches", () => {
        expect(names("BOX")).toEqual(["devbox", "status"])
        expect(names("zzz")).toEqual([])
    })
})
