export const guide = {
  title: "Play Style Guide",
  intro:
    "A list of play styles. Those that are off by default can be turned on here, which adds them to the main menu. You can change these settings anytime from the settings screen.",
  enable: "Enable",
  addedToMenu: "Added to the menu",
  openSettings: "Open settings",
  sections: {
    basics: "Basic screens",
    features: "More ways to play",
  },
  newGame: {
    title: "Normal Play",
    desc: "Give the character dress-up, reality-alteration or action instructions, and an image and inner monologue are generated. The mental parameters (bloom / shame / adaptation) change as you play, with endings and achievements.",
    note: "Choose request mode on the new-play screen and the character asks you for the look they want. Fulfil the wish by dressing them up, and work out their hidden preferences from reactions and hints.",
  },
  gallery: {
    title: "Gallery",
    desc: "Look back at past sessions and generated images. Images you like can be saved as favorites.",
  },
  characters: {
    title: "Characters",
    desc: "Create and manage characters. With a portrait (an uploaded image works too), you can start a play with that character. Set a name, personality, speech style, look and voice, and you can talk with them as that character in Character Chat.",
    note: 'Starting a play from your own image has moved here from "Or use your own image" on the new-play screen. That entry on the new-play screen is deprecated and will be removed in v0.12.0.',
  },
  records: {
    title: "Endings & Achievements",
    desc: "Look back at the endings you have reached and the achievements you have unlocked.",
  },
  settings: {
    title: "Settings",
    desc: "Change the difficulty, NSFW, language, image and text providers, read-aloud and more.",
    note: 'The "Preference Memory", which summarizes your tastes from past play, is also generated and edited in the settings screen.',
  },
  adventure: {
    title: "TSF Scenario",
    desc: "A standalone novel game that starts from a transformed state. Five mission types including a romance simulation, with reality alteration and automatic BGM selection.",
    note: 'Each turn runs text and image generation, so wait times are longer than in normal play. You can preview the BGM with "BGM Test" in the menu.',
    open: "Open TSF Scenario",
  },
  talk: {
    title: "Talk & Face-to-Face Mode",
    desc: "During the romance simulation, you can converse one exchange at a time in face-to-face mode. Free chat that does not spend a turn (Talk) opens Character Chat from the action panel, and what you talk about carries into the next scene.",
    note: "Face-to-face mode is turned on in the romance simulation's start screen and image settings; Talk needs Character Chat enabled.",
    open: "Open Character Chat",
    enableParent: "Enable Character Chat first",
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
  characterChat: {
    title: "Character Chat",
    desc: "Talk one-on-one with a character outside the TSF scenario. The guide character Serena remembers your tastes and past play and looks things up when you ask about recent sessions or tendencies. You can also bring back a character from a past session with the feelings they had at that point, choose the appearance from past images, and ask for a change of clothes to redraw the portrait.",
    note: 'Each reply first decides what to look up, so replies take a little longer than a plain chat. Asking for a change of clothes also runs image generation. Optionally, turning on "Let Serena check the weather" and "Let Serena search the web" in the settings screen lets her look up the weather and recent topics on the web (requires server-side setup).',
    open: "Open Character Chat",
  },
  salon: {
    title: "Salon Management",
    desc: "Run a salon for 12 weeks, making your customers' wishes come true with a change of look. Serving works like request mode: ask counselling questions to draw out clues to tastes the customer keeps unsaid, then finish the look in 3 styling turns. The satisfaction at checkout decides sales and reputation, and higher reputation brings more bookings.",
    note: "The difficulty you choose when opening sets the opening funds. Cover the weekly fixed costs with your sales and end the season with more cash than you started with. Each styling turn generates an image, and the questions and reviews use text generation. Opening a salon and closing a week play a short scene; choose Full, Short or Off in the owner's office. The ⚙ on the serving screen changes the direct prompt, negative prompt, i2i strength, and the image and text models (shared with the right panel in normal play).",
    open: "Open Salon Management",
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
};
