export const character = {
  panel: {
    title: "Characters",
    description:
      "On-stage characters are reflected in image generation and in the inner-voice, action and chat text. When a personality is set, that character's pronoun and tone are reflected in the text.",
    add: "Add",
    adding: "Adding…",
    delete: "Delete",
    edit: "Edit",
    close: "Close",
    empty: "No characters registered yet.",
    featureToggle: "Enabled",
    featureToggleHint:
      "When OFF, multi-person mode itself stays active, but this panel's characters are no longer reflected in images or text (rolls back to the pre-v0.5.0 multi-person behavior).",
    disabledNote:
      "While OFF, registered characters are not reflected in images or text. Their settings are kept.",
    protagonist_badge: "Lead",
    editCast: "Edit characters",
    editOne: "Edit {{name}}'s look and personality",
    groups: "Combinations",
    onStageCount: "On stage {{count}} / {{limit}}",
    overLimit:
      "The current image model can draw up to {{limit}} people in one image. Characters at the end of the list are not used for generation. Turn some of them off stage.",
    alwaysOnStage: "The lead is always on stage",
    onStageLimitReached:
      "The current image model's limit of {{limit}} on-stage characters has been reached",
    notUsed:
      "Not used for generation: beyond the {{limit}} people the current image model can draw in one image",
  },
  field: {
    name: "Name",
    appearance_natural: "Appearance (free text)",
    appearance_tags: "Appearance tags (NovelAI format)",
    negative_tags: "Negative tags (things not to draw on this character)",
    negative_tags_placeholder: "e.g. glasses, beard, hat",
    position: "Position",
    appearance_lock: "Fix the look (always draw it as set)",
    exclude_from_effects: "Exclude from effects (not affected by instructions)",
    on_stage: "On stage",
    on_stage_of: "Put {{name}} on stage",
  },
  position: {
    left: "Left",
    "center-left": "Center left",
    center: "Center",
    "center-right": "Center right",
    right: "Right",
  },
  badge: {
    appearance_lock: "Look fixed: always drawn as set",
    lock_short: "Fixed",
    exclude_from_effects: "Excluded from effects: instructions don't affect it",
    bystander_short: "Excluded",
    profile: "Personality is set",
    profile_short: "Persona",
    not_used_short: "Over limit",
    look_changed:
      "The look changed from the setting in the last turn (the next turn carries it over)",
    look_changed_short: "Changed",
  },
  save_status: {
    saved: "Saved",
    saving: "Saving…",
    dirty: "Unsaved",
    error: "Save failed",
  },
  error: {
    name_required: "Please enter a name",
    limit_exceeded: "Up to {{max}} characters per session, including the lead",
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
    overwrite_confirm:
      'A preset named "{{name}}" already exists. Overwrite it?',
    delete_confirm: 'Delete "{{name}}"?',
    deleting: "Deleting…",
    apply_to_protagonist: "Apply to lead",
    apply_to_protagonist_title:
      "Overwrite the current lead's appearance with this preset",
    apply_to_protagonist_confirm:
      'Overwrite the lead "{{name}}" with "{{preset}}"?',
  },
  cast: {
    title: "Character settings",
    registeredCount: "Registered {{count}} / {{max}}",
    add: "Add character",
    addFromPreset: "Add from preset",
    newName: "Character {{number}}",
    appearanceSection: "Look setting",
    currentLookSection: "Current look (result of the last turn)",
    currentLookHistory:
      "The next turn carries this look over. The look setting fields are not rewritten.",
    currentLookSpecNext:
      "The setting is newer than the last turn, so the next turn draws the set look. Below is the look drawn in the last turn.",
    currentLookFixed: "The look is fixed, so every turn draws the set look.",
    currentLookEmpty: "No turn result yet. The next turn draws the set look.",
    copyToSpec: "Copy to setting",
    copyToSpecConfirm:
      "Replace the current appearance tags with the tags of the current look?",
    resetLook: "Go back to the set look (from the next turn)",
    resetLookUnavailable: "The next turn already draws the set look",
    generateTags: "Make tags from the text",
    generatingTags: "Making tags…",
    generateTagsError: "Couldn't make tags",
    generateTagsConfirm:
      "Replace the current appearance tags with tags made from the text?",
    generateTagsNeedNatural: "Enter the appearance text first",
    tagsHint:
      "Images use the tags. The text is used only when the tags are empty.",
    naturalChangedHint:
      'You changed the text, but images still use the current tags. If needed, use "Make tags from the text" to remake them.',
    profileSection: "Personality",
    pickAppearance: "Choose look",
    pickerTitle: "Choose {{name}}'s look",
    resolving: "Loading look…",
    resolveError: "Couldn't load the chosen look",
    overwriteAppearanceConfirm:
      "Replace the current appearance (text and tags) with the chosen look?",
    noThumbnail: "No look chosen",
    protagonistProfileNote:
      "The lead's personality comes from the character settings, or from the self-mode character settings.",
    savePreset: "Save this character as a preset",
    deleteCharacter: "Delete this character",
  },
  profile: {
    memo: "Personality notes",
    memoPlaceholder:
      "e.g. The lead's childhood friend. Caring and a bit meddlesome. Good at cooking.",
    generate: "Generate personality from notes",
    generating: "Generating…",
    generateError: "Failed to generate the personality",
    generateHint:
      "With empty notes, the personality is based on the name and appearance. You can edit the result below.",
    genderUnset: "Not set",
  },
  group: {
    title: "Character combinations",
    description:
      "Save every character except the lead (appearance, negative tags, personality, on-stage state) together, and load them in another session.",
    namePlaceholder: "Combination name",
    saveCurrent: "Save current characters as a combination",
    saving: "Saving…",
    saved: 'Saved "{{name}}"',
    overwriteConfirm:
      'A combination named "{{name}}" already exists. Overwrite it with the current characters?',
    apply: "Switch to this combination",
    applying: "Switching…",
    applyConfirm:
      'Replace every character except the lead with the {{count}} characters in "{{name}}"? The current characters (except the lead) will be removed.',
    applied: 'Switched to "{{name}}".',
    delete: 'Delete combination "{{name}}"',
    deleteConfirm: 'Delete the combination "{{name}}"?',
    empty: "No saved combinations.",
    loading: "Loading…",
    memberCount: "{{count}}",
    showMembers: "Show members",
    hideMembers: "Hide members",
    offStage: "off stage",
    nothingToSave:
      "There are no characters besides the lead, so there is nothing to save",
  },
};
