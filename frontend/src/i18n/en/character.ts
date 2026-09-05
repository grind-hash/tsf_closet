export const character = {
  panel: {
    title: "Characters",
    description:
      "Character data registered here is only reflected in image generation prompts (it does not affect chat responses).",
    add: "Add",
    adding: "Adding…",
    delete: "Delete",
    edit: "Edit",
    close: "Close",
    empty: "No characters registered yet.",
    featureToggle: "Enabled",
    featureToggleHint:
      "When OFF, multi-person mode itself stays active, but this panel's character data is no longer injected into image prompts (rolls back to the pre-v0.5.0 multi-person behavior).",
  },
  field: {
    name: "Name",
    appearance_natural: "Appearance (free text)",
    appearance_tags: "Appearance tags (NovelAI format)",
    position: "Position",
  },
  save_status: {
    saved: "Saved",
    saving: "Saving…",
    dirty: "Unsaved",
    error: "Save failed",
  },
  error: {
    name_required: "Please enter a name",
    limit_exceeded: "Up to 4 characters per session",
  },
  confirm: {
    delete: "Delete {{name}}?",
  },
  preset: {
    apply_button: "Presets",
    picker_title: "Add from preset",
    loading: "Loading…",
    empty: "No saved presets.",
    apply: "Apply",
    applying: "Applying…",
    save: "Save preset",
    saving: "Saving…",
    save_prompt: "Enter preset name",
  },
};
