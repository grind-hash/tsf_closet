export const guide = {
  title: "Play Style Guide",
  intro:
    "A list of play styles. Those that are off by default can be turned on here, which adds them to the main menu. You can change these settings anytime from the settings screen.",
  enable: "Enable",
  addedToMenu: "Added to the menu",
  detailsShow: "Show details",
  detailsHide: "Hide details",
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
    desc: "Run a salon, making your customers' wishes come true with a change of look. Choose a season of 4 weeks (quick) or 12 weeks (full), and after each settlement you can carry your cash and reputation into the next season. Serving works like request mode: ask counselling questions to draw out clues to tastes the customer keeps unsaid, then finish the look in 3 styling turns. The satisfaction at checkout decides sales and reputation, and higher reputation brings more bookings and bigger tips when you grant a wish.",
    note: "The difficulty and season length you choose when opening set the opening funds. Each styling turn generates an image, and the questions and reviews use text generation.",
    details: [
      {
        heading: "Running the salon",
        items: [
          "Cover the weekly fixed costs with your sales and end the season with more cash than you started it with.",
          "Customer type, on the opening screen and in the owner’s office, picks the customers (everyone, men or women) and the body they wish for (auto, female or male). Men wishing for a female body brings only men who want to become women. The customer setting applies from next week’s bookings and the body from the next customer you serve.",
          "Opening a salon and closing a week play a short scene; choose Full, Short or Off in the owner’s office.",
        ],
      },
      {
        heading: "Serving",
        items: [
          "The top of the serving screen shows the satisfaction, with the change since the last styling turn and the line that grants the wish.",
          "The message window shows a chart of the kinds of taste the customer keeps unsaid (✓ when granted, ◆ for the one on their mind). In counselling, press a kind on the chart to write a question about it.",
          "A perfect finish (satisfaction 100) doubles the course price, and granting the wish of a regular who came back in your look adds a regular’s fee.",
          "You can send home a customer you have not styled yet (reputation −3). You can close the week while serving; a styled customer is checked out at the current satisfaction.",
        ],
      },
      {
        heading: "Styling tools",
        items: [
          "The ⚙ on the serving screen changes the direct prompt, negative prompt, i2i strength, and the image and text models (shared with the right panel in normal play).",
          '"Select area" next to the styling instruction lets you paint or pick a mask for the part to restyle (NovelAI only; the area is kept while you serve that customer).',
          'While styling, "Compare" at the top right of the message window shows the look side by side with the previous one or the look on arrival.',
        ],
      },
    ],
    open: "Open Salon Management",
  },
  hakoniwa: {
    title: "AI Dollhouse",
    desc: 'Watch residents live on their own in Stardust House, a small boarding house. Each time you press "Advance the day", three events happen and pile up in the chronicle. As the unseen writer, you can rewrite how the world works with rules, transform the residents, and order scenes.',
    note: "Events, words and chats use text generation; transformations, looks and scene pictures use image generation (choose the image model per world on the Settings tab).",
    details: [
      {
        heading: "A day in the dollhouse",
        items: [
          'Press "Advance the day" and three events happen: the residents gather in the room and talk in speech bubbles (click or Enter for next, Esc to skip).',
          'Events are kept in the chronicle, and moods and relationships change little by little. After playback, a "Day N recap" shows the highlight, what changed most, and a hint of tomorrow.',
          '"Tomorrow’s intervention" next to "Advance the day" lets you pick one push for the next day, such as a gentle nudge or stronger rewrites. The choices change with the situation, and the result appears in the recap.',
          "Multi-day stories (swapped days, a new look, the distance between two residents, investigating the world) arise and reach their climax on their third event.",
        ],
      },
      {
        heading: "Creating a world",
        items: [
          "Besides the 5 residents of Stardust House, you can bring in characters you made on the Characters screen (those with a portrait) or residents you write yourself.",
          '"Random residents" puts together residents with different names, personalities and looks (swap them out one by one; uses text generation). "Generate looks for residents without a portrait" on the Residents tab draws missing portraits one at a time.',
          "Pick an experiment theme (keep the swap going, a week of the dress rule, grow the strangeness to a confrontation, transformation experiment, free experiment, or write your own) and its progress appears in the recap. A theme you write also gently shapes events and conversations.",
          "On day 1 of a new world, a getting-started guide appears (you can fold or close it).",
          "Whatever you write in the world memo on the Settings tab takes precedence over the rules in every generation.",
        ],
      },
      {
        heading: "Places and furniture",
        items: [
          "Stardust House has a living room, a garden and a study; switch the place you watch with the chips above the room. Residents move to where their events happen and wander between places as days pass.",
          "On the Furniture tab, place up to four pieces in each place (each piece is one of a kind, and placed furniture may appear in events when it fits).",
        ],
      },
      {
        heading: "Talking with residents",
        items: [
          'Click a resident in the room, or press "Hear a word" on the Residents tab, to hear a word that fits their mood.',
          '"Chat" lets you type messages and talk for as long as you like. Asking "Put on ..." or "Change back" transforms them or undoes it on the spot.',
          'When you pick a resident on the Residents tab, the tabs under their name switch between "Transform / Event", "Profile" (personality, relationships and memories) and "Looks & edit".',
          "Press a portrait to enlarge it and touch the head, chest or below the waist (the mood shifts a little and nothing goes into the chronicle).",
          'Residents remember transformations, swaps and events that moved a relationship a lot ("Remembers" under "Profile"), and may bring them up later.',
          'When editing a resident, choose how they call the other residents (given name, family name, with or without an honorific); event and chat lines use it. Random residents get a style that fits their personality, and much older housemates get an honorific. "Relationships" under "Profile" shows what each resident calls the others.',
        ],
      },
      {
        heading: "Rules",
        items: [
          "Up to 3 rules (Ladylike Speech, The Swapped Morning, Rule of Dresses, Romance Ban, Confession Week, and rules you write) can be active at once, and they affect every event from the next day on. Switching a rule makes the residents nearby react briefly (not kept in the chronicle).",
          'Built-in rules have combos (such as swap and dresses): with both active, the Rules tab shows "In effect" and events reflect it.',
          'The look of your own rule is set by its look tags (a rule with no tags and no body sex change does not change looks). "Generate looks" on the Rules tab generates a rule look for every resident, one at a time. When two or more look rules overlap (the Rule of Dresses counts too), you can also generate a combined look.',
          'Choosing "Make female" or "Make male" under "Body sex" on your own rule turns the body of every resident into that sex in the rule look, and events are written with the new body (writing the sex in the look description does not change it). A rule can also change only the body sex, with no look tags. After changing it, generate the looks again.',
        ],
      },
      {
        heading: "Transformations and looks",
        items: [
          '"Transform on the spot" under "Transform / Event" generates a new look (nearby residents’ reactions are added to the chronicle).',
          "Looks are shown in the order transformation → combined look → rule look (the rule turned on last) → dress → usual, and events and scene pictures use the same look.",
          "A transformation belongs to the body: transforming a swapped resident changes the body they are in now, and when the swap ends the transformed body goes back to its owner.",
          "The resident and the others get used to a transformation or swap day by day (bewildered → trial and error → getting used to it → accepted). After changing back, a remnant lingers for a few days.",
          'Images of residents (usual and dress looks) and your own rules use the tags in the form as they are. "Make tags from the description" fills the field with tags made from the description (saved only when you save). You can edit the tags by hand; changing the description does not change them. A resident needs usual look tags. To redraw, generate the look again after saving.',
          "With NAI Diffusion V5, looks are generated with a transparent background; with other settings (V4.5 or other providers) they are generated on white and made transparent when shown.",
        ],
      },
      {
        heading: "Ordering events",
        items: [
          'Switch the toggle under "Transform / Event" to "Event" to generate one scene that follows your order with the residents in their current looks, without changing them, and read it as a scene (uses text generation).',
          'Choose who takes part: only them, chosen residents (up to 2) or roommates. It stays in the chronicle as an "Ordered event" and affects mood, relationships, memories and world strangeness.',
          "Besides Auto, the place can be the bathroom, bedroom, kitchen, shopping street, cafe, park, beach or hotel, which becomes the background of the scene picture (daily events also happen there when they fit).",
          "No romantic or sexual scene is written between two residents who both have male bodies right now.",
        ],
      },
      {
        heading: "Scenes and scene pictures",
        items: [
          '"Read as a scene" in the chronicle lets you read an event one beat at a time with a background and portraits. "Log" at the top right of the message window lets you reread what you have already read (for a continued scene, it goes back through the earlier scenes).',
          '"Continue scene" lets you order how any of today’s events continues, with the same residents in the same place (your order can move them). It stays in the chronicle as an "Ordered continuation", and world strangeness rises only a little.',
          '"Draw this scene" generates one picture of the event’s residents in their current looks. Events with contact or closeness are marked "Worth a picture".',
          "The outfit changes to fit the scene only in the picture (nude or a towel in the bathroom, a swimsuit at the beach and so on; nude only with NSFW mode on). The residents’ looks and portraits stay the same.",
        ],
      },
      {
        heading: "World strangeness and records",
        items: [
          'In worlds that use "world strangeness" (set when creating the world or on the Settings tab; on by default), switching rules and transforming residents makes them notice the rewrites (stillness → stirring → probing), and at 80 they call out to the writer once. The stage and value appear in the top bar.',
          "What you observe in the dollhouse (days, events, rules, transformations, dresses, swaps, strangeness and more, 17 records) is counted across all worlds and recorded under AI Dollhouse on the Achievements screen.",
        ],
      },
    ],
    open: "Open AI Dollhouse",
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
