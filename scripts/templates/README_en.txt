============================================
  TSF Closet  ─  Read Me First
============================================

  Thank you for downloading TSF Closet.

  This file explains how to set up and
  start playing for first-time users.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Initial Setup (Required before first use)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  This game uses NovelAI services
  for image and text generation.
  You need a NovelAI "API Key" to play.

  ── How to get a NovelAI API Key ──

  1. Log in to the NovelAI website
     https://novelai.net

  2. Click the gear icon at the top left
     and open "Account" settings

  3. Click "Get Persistent API Token"

  4. The long string displayed (starting with pst-)
     is your API key. Copy it.

     * The API key is shown only once.
       We recommend saving it in a text file.
     * Do not share this key with anyone.

  ── How to set up config.env ──

  1. Right-click the "config.env" file
     in this folder and open it with Notepad

     * If asked to choose a program,
       select "Notepad"

  2. Find the following line in the file:

       NOVELAI_API_KEY=your_api_key_here

  3. Replace "your_api_key_here" with
     the API key you copied

     Example:
       NOVELAI_API_KEY=pst-abc123xxxxx...

     * Do not add spaces around the = sign
     * Do not wrap the API key in " or '

  4. Save the file using
     File > Save in Notepad

  Initial setup is now complete!


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  How to Start the Game
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Double-click "start.bat" in this folder

  2. A black console window will open.
     Wait a moment for it to finish loading.

  3. Your browser will open automatically
     and show the game screen

  4. If the browser does not open,
     enter the following URL
     in your browser's address bar:

       http://127.0.0.1:8000


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Changing the Language
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  This game supports Japanese and English.
  The default language is Japanese.

  To switch to English:

  1. Click the ⚙ (gear) icon
     at the top right of the game screen

  2. In the Settings screen, find the
     "言語" (Language) section

  3. Select "English" to switch

  The change takes effect immediately.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  How to Stop the Game
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  You can stop the game in either way:

  - Click the X button at the top right
    of the black console window

  - Press Ctrl + C on your keyboard
    while the console window is focused


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Requirements
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - Windows 11 PC (64-bit)
  - Internet connection
  - NovelAI paid plan (subscription)
  - Microsoft Visual C++ Redistributable

  * Image and text generation will not work
    without a NovelAI paid subscription.
  * Each image generation consumes NovelAI Anlas.
    The Opus plan offers unlimited
    normal-size generation.

  ── About Visual C++ Redistributable ──

  This game requires the
  "Microsoft Visual C++ Redistributable"
  package.

  Most PCs already have it installed,
  but if you see "DLL load failed" or
  "The specified module could not be found"
  errors on startup, please install it from:

    https://aka.ms/vs/17/release/vc_redist.x64.exe

  * Paste the URL above into your browser
    to start the download.
  * Run the downloaded exe file and follow
    the on-screen instructions.
  * No PC restart is required after installation.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  About NovelAI Plans
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  We recommend the "Opus" plan
  for the best experience.

  Reasons:
  - Unlimited normal-size image generation
  - Text generation (character thoughts) available
  - No need to worry about Anlas balance

  Tablet / Scroll plans also work,
  but each image generation consumes Anlas,
  so watch your monthly usage.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Customizing Settings (Advanced)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  You can change settings by editing
  config.env with a text editor.
  The defaults work fine for most users.

  PORT
    Server port number (default: 8000).
    Change only if it conflicts with
    other software.

  LOG_LEVEL
    Log verbosity (default: info).
    Change to "debug" for more detailed
    information when troubleshooting.

  NOVELAI_STEPS
    Image generation steps (default: 28).
    Higher values may improve quality
    but increase generation time.

    * IMPORTANT *
    Even on the Opus plan, setting steps
    to 29 or higher will consume Anlas.
    28 or below is Anlas-free.
    Leave it at 28 unless you have
    a specific reason to change it.

  NOVELAI_I2I_STRENGTH
    Image variation strength (default: 0.90).
    Closer to 1.0 = more change.
    Closer to 0.0 = closer to original image.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Data Storage Location
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Save data and generated images
  are stored in:

    backend\data\

  To back up your data, copy this
  entire folder.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FAQ (Troubleshooting)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Q: Double-clicking start.bat does nothing

  A: Check the following:
     - Did you extract the ZIP file first?
       It won't work if run from inside the ZIP.
     - Does the folder path contain
       non-ASCII characters (e.g. Japanese)?
       -> Place it in an ASCII-only folder
         Example: C:\Games\TSFCloset\

  ─────────────────────

  Q: "Port is already in use" error appears

  A: Another program may be using
     the same port (8000).
     Change PORT in config.env
     to a different number (e.g. 8080).

  ─────────────────────

  Q: Browser does not open automatically

  A: Enter http://127.0.0.1:8000
     directly in your browser's address bar.

  ─────────────────────

  Q: Image generation fails / errors occur

  A: Check the following:
     - Is NOVELAI_API_KEY set correctly
       in config.env?
     - Is your NovelAI subscription active
       (not expired)?
     - Are you connected to the internet?
     - Do you have Anlas remaining?
       * Opus plan has unlimited normal-size

  ─────────────────────

  Q: I lost my API key

  A: Log in to the NovelAI website,
     go to Account > "Get Persistent API Token"
     to generate a new key.
     Set the new key in config.env.

  ─────────────────────

  Q: I want to move save data to another PC

  A: Copy the entire backend\data\ folder
     and place it in the same location
     on the destination PC.


============================================
