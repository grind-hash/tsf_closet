export const guide = {
  title: "Play Style Guide",
  intro:
    "A list of play styles that are off by default. Turning one on here adds it to the main menu. You can change these settings anytime from the settings screen.",
  enable: "Enable",
  addedToMenu: "Added to the menu",
  openSettings: "Open settings",
  adventure: {
    title: "TSF Scenario",
    desc: "A standalone novel game that starts from a transformed state. Five mission types including a romance simulation, with reality alteration and automatic BGM selection.",
    note: "Each turn runs text and image generation, so wait times are longer than in normal play.",
    open: "Open TSF Scenario",
  },
  talk: {
    title: "Talk & Face-to-Face Mode",
    desc: "During the romance simulation, you can chat without spending a turn (Talk) and converse one exchange at a time in face-to-face mode. Combine them with line read-aloud and microphone input.",
    note: "Face-to-face mode can be turned on in the romance simulation's start screen and image settings.",
    open: "Open TSF Scenario",
    enableParent: "Enable TSF Scenario first",
  },
  inventory: {
    title: "Inventory System",
    desc: "In the TSF Scenario, things you obtain through conversation and events are tracked as items you can give, use, wear, or discard. Saying you have something does not make it yours; the other person's will and social norms decide the outcome, and a reality alteration can rewrite it directly.",
    note: 'Turn it on with "Enable the inventory system" on the scenario start screen or in the image settings. It greatly changes how the scenario plays out.',
    open: "Open TSF Scenario",
    enableParent: "Enable TSF Scenario first",
  },
  vrm: {
    title: "3D Model (VRM)",
    desc: "Shows a 3D model instead of the partner's portrait in face-to-face mode. The mouth moves with the voice, and the expression and gesture change with every reply.",
    note: 'Register VRM (0.x / 1.0) model files under "3D Model (VRM)" in the settings screen.',
  },
  promptExpander: {
    title: "Prompt Expander",
    desc: "Builds image-generation prompts from natural sentences and generates and saves images independently of the game. Manga (panel) mode is also supported.",
    note: "NovelAI provider only.",
    open: "Open Prompt Expander",
  },
  voice: {
    title: "Line Read-Aloud (Speech Synthesis)",
    desc: "Reads character lines aloud. Available in normal-play chat and in the TSF Scenario's face-to-face mode.",
    note: 'Requires the AivisSpeech engine. Set it up under "Speech Synthesis (AivisSpeech)" in the settings screen.',
  },
  playMemory: {
    title: "Play Memory",
    desc: "Automatically summarizes the course of each play and feeds it into later generation. Settings you want to keep can be written as a user memo.",
    note: "When enabled, an auto memo is generated per response, so completion may take longer.",
    enabledHint:
      'A "Play Memory" panel appears on the right side of normal play',
  },
  endings: {
    title: "Endings",
    desc: "Endings trigger when their conditions are met, and you can review them in the list screen.",
    note: "When enabled, ending notifications and the endings menu are shown.",
    open: "Open the endings list",
  },
};
