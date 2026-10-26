import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CharacterPreset } from "../../types";
import "../../i18n";
import CharacterSettingsEditor from "./CharacterSettingsEditor";

const mocks = vi.hoisted(() => ({
  updateCharacterPreset: vi.fn(),
  generateCharacterProfile: vi.fn(),
}));

vi.mock("../../apis/characters", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/characters")>()),
  updateCharacterPreset: mocks.updateCharacterPreset,
  generateCharacterProfile: mocks.generateCharacterProfile,
}));

vi.mock("../../apis/avatars", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/avatars")>()),
  listAvatarModels: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../apis/speechSynthesis", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/speechSynthesis")>()),
  getAivisSpeakers: vi.fn().mockResolvedValue([
    {
      name: "まい",
      speaker_uuid: "spk-1",
      styles: [
        { id: 11, name: "ノーマル" },
        { id: 12, name: "あまあま" },
      ],
    },
  ]),
}));

const PRESET: CharacterPreset = {
  id: "p1",
  name: "サクラ",
  appearance_natural: "",
  appearance_tags: "1girl, pink hair",
  default_position: "center",
  negative_tags: "",
  profile: {
    personality: "明るい",
    reaction_style: "default",
    pronoun: "私",
    gender: "woman",
    interests: [],
    tsf_attitude: "",
    memo: "",
    speech_style: "",
    sample_lines: "",
    knowledge: "喫茶店で働いている",
    greeting: "",
  },
  thumbnail_url: null,
  avatar_model_id: null,
  voice: null,
  portrait_url: null,
  created_at: "2026-10-26T00:00:00",
  updated_at: "2026-10-26T00:00:00",
};

beforeEach(() => {
  localStorage.clear();
  mocks.updateCharacterPreset.mockReset();
  mocks.updateCharacterPreset.mockImplementation(
    async (_id: string, payload: Partial<CharacterPreset>) => ({
      ...PRESET,
      ...payload,
    }),
  );
  mocks.generateCharacterProfile.mockReset();
});

afterEach(() => {
  cleanup();
});

function renderEditor(onSaved = vi.fn()) {
  render(
    <CharacterSettingsEditor
      preset={PRESET}
      onSaved={onSaved}
      sectionStorageKey="test_sections"
    />,
  );
  return onSaved;
}

describe("CharacterSettingsEditor", () => {
  it("saves a text field with the rest of the profile on blur", async () => {
    const onSaved = renderEditor();
    const field = screen.getByLabelText("口調・話し方");
    fireEvent.change(field, { target: { value: "丁寧語" } });
    fireEvent.blur(field);
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [, payload] = mocks.updateCharacterPreset.mock.calls[0];
    expect(payload.profile).toMatchObject({
      speech_style: "丁寧語",
      personality: "明るい",
      knowledge: "喫茶店で働いている",
    });
  });

  it("keeps knowledge when drafting the personality with the LLM", async () => {
    mocks.generateCharacterProfile.mockResolvedValue({
      personality: "おっとり",
      reaction_style: "gentle",
      pronoun: "わたし",
      gender: "woman",
      interests: ["紅茶"],
      tsf_attitude: "",
      memo: "",
      knowledge: "",
    });
    renderEditor();
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "LLM で性格を下書き" }),
      );
    });
    await waitFor(() => expect(mocks.updateCharacterPreset).toHaveBeenCalled());
    const [, payload] = mocks.updateCharacterPreset.mock.calls[0];
    expect(payload.profile).toMatchObject({
      personality: "おっとり",
      pronoun: "わたし",
      knowledge: "喫茶店で働いている",
    });
  });

  it("picks the speaker's first style when choosing a voice", async () => {
    renderEditor();
    const select = await screen.findByLabelText("声");
    await waitFor(() =>
      expect((select as HTMLSelectElement).disabled).toBe(false),
    );
    fireEvent.change(select, { target: { value: "spk-1" } });
    await waitFor(() =>
      expect(mocks.updateCharacterPreset).toHaveBeenCalledWith("p1", {
        voice: { speaker_id: "spk-1", style_id: "11" },
      }),
    );
  });

  it("rejects an empty name without saving", async () => {
    renderEditor();
    const field = screen.getByLabelText("名前");
    fireEvent.change(field, { target: { value: "  " } });
    fireEvent.blur(field);
    await waitFor(() =>
      expect(
        screen
          .getAllByRole("status")
          .some((node) => node.className.includes("save-status--error")),
      ).toBe(true),
    );
    expect(mocks.updateCharacterPreset).not.toHaveBeenCalled();
  });
});
