export const characters = {
  title: "Characters",
  intro:
    "Create and manage the characters you talk with in Character Chat. Set the name, first-person pronoun, personality, speech style, knowledge, look, 3D model and voice, then start a conversation as that character. Characters you make can also join normal play as cast members.",
  create: "Create a new character",
  creating: "Creating...",
  newName: "New character",
  empty: "No characters yet.",
  loading: "Loading...",
  talk: "Talk with this character",
  talking: "Preparing the conversation...",
  edit: "Edit",
  delete: "Delete this character",
  deleteTitle: "Delete this character?",
  deleteBody:
    "The settings and portrait of {{name}} will be deleted. Conversations with this character stay and continue with the current name and pronoun. This cannot be undone.",
  deleteConfirm: "Delete",
  cancel: "Cancel",
  back: "Back to list",
  notFound: "This character was not found.",
  badgeVrm: "3D",
  badgeVoice: "Voice",
  noPersonality: "No personality set",
  sections: {
    profile: "Name and personality",
    speech: "Speech",
    knowledge: "Knowledge and background",
    appearance: "Look and portrait",
    avatarVoice: "3D model and voice",
    greeting: "Opening line",
  },
  fields: {
    name: "Name",
    memo: "Notes",
    memoPlaceholder:
      "Notes on the character's mood or setting. Used as hints for “Draft the personality with the LLM”.",
    speechStyle: "Speech style",
    speechStylePlaceholder: "e.g. Polite, and calls the user “senpai”",
    sampleLines: "Sample lines",
    sampleLinesPlaceholder:
      "One per line. e.g.\n“Welcome back, senpai.”\n“Oh, you're hopeless.”",
    sampleLinesHint:
      "Given as a model of the character's voice. The character does not repeat them as is.",
    knowledge: "Knowledge and background",
    knowledgePlaceholder:
      "Upbringing, job, likes, relationship with the user, and so on. Treated as facts for the character.",
    greeting: "Opening line",
    greetingPlaceholder: "e.g. Welcome. What shall we talk about today?",
    greetingHint:
      "Shown as the character's first message when a new conversation starts. When empty, you start the conversation.",
    appearanceNatural: "Look (natural language)",
    appearanceTags: "Appearance tags",
    appearanceTagsHint:
      "Used to draw the portrait and as the starting look in Character Chat. When there is no gender tag (such as 1girl), it is filled in from the personality's gender.",
    vrm: "3D model",
    vrmNone: "None (show the portrait)",
    vrmMissing: "The chosen 3D model has been deleted.",
    vrmHint:
      "Shows this character as a 3D model in Character Chat. You can still switch models from the Appearance menu during a conversation.",
    voice: "Voice",
    voiceDefault: "Use the voice from Settings",
    voiceLoading: "Loading AivisSpeech speakers...",
    voiceUnavailable:
      "Could not load AivisSpeech speakers. Enable speech synthesis in Settings to choose one.",
    voiceHint: "The voice used to read replies aloud in Character Chat.",
  },
  generateProfile: "Draft the personality with the LLM",
  generatingProfile: "Drafting...",
  generateProfileHint:
    "Fills in personality, pronoun, gender, interests and so on from the name, look and notes. Speech style, sample lines and knowledge are kept.",
  generateProfileError: "Could not draft the personality.",
  generateTags: "Make tags from the description",
  generatingTags: "Making tags...",
  generateTagsNeedNatural: "Enter a natural-language look to make tags.",
  generateTagsConfirm:
    "Replace the current appearance tags with tags made from the description?",
  generateTagsError: "Could not make appearance tags.",
  portrait: {
    title: "Portrait",
    none: "No portrait yet.",
    import: "Use an image as the portrait",
    importTitle: "Choose an image for the portrait",
    importHint:
      "Uses an image from a session, favorite or Prompt Expander as is. When the appearance tags are empty, the image's look is imported too.",
    generate: "Draw a portrait from the tags",
    generating: "Drawing the portrait...",
    generatingHint:
      "Image generation can take about a minute. Keep this screen open until it finishes.",
    needTags: "Enter appearance tags to draw a portrait.",
    precise: "Use precise reference",
    preciseHint:
      "Sends the current portrait as a precise reference (character reference); each reference costs extra Anlas.",
    anlasBody:
      "The portrait will be drawn with a precise reference. Each reference costs extra Anlas. Continue?",
    imported: "The image is now the portrait.",
    importedWithTags:
      "The image is now the portrait, and its appearance tags were imported.",
  },
  preview: {
    title: "Preview",
    vrmLoading: "Loading the 3D model...",
    talkHint:
      "Opens the latest conversation with this character, or starts a new one.",
  },
  errors: {
    loadFailed: "Could not load the character.",
    saveFailed: "Could not save.",
    createFailed: "Could not create the character.",
    deleteFailed: "Could not delete the character.",
    talkFailed: "Could not start the conversation.",
    portraitFailed: "Could not draw the portrait.",
    importFailed: "Could not use the image as the portrait.",
  },
};
