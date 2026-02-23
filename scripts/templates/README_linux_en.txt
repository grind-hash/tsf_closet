============================================
  TSF Closet (Linux)  ─  Read Me First
============================================

  Thank you for downloading TSF Closet.

  This file explains how to set up and
  start playing on Ubuntu/Linux.


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

  1. Open the "config.env" file in this folder
     with a text editor

     Examples:
       nano config.env
       gedit config.env
       vim config.env

  2. Find the following line in the file:

       NOVELAI_API_KEY=your_api_key_here

  3. Replace "your_api_key_here" with
     the API key you copied

     Example:
       NOVELAI_API_KEY=pst-abc123xxxxx...

     * Do not add spaces around the = sign
     * Do not wrap the API key in " or '

  4. Save the file

  Initial setup is now complete!


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  How to Start the Game
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Open a terminal, navigate to this folder,
     and run start.sh

     cd /path/to/tsf_closet_portable
     ./start.sh

     * If you get a permission error:
       chmod +x start.sh
       then try again

  2. Log output will appear in the terminal.
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

  - Press Ctrl+C in the terminal

  - Run stop.sh from another terminal:
    ./stop.sh


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Requirements
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  - Ubuntu 22.04 or later (64-bit) or other
    Linux distributions
  - Internet connection
  - NovelAI paid plan (subscription)

  * Image and text generation will not work
    without a NovelAI paid subscription.
  * Each image generation consumes NovelAI Anlas.
    The Opus plan offers unlimited
    normal-size generation.


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

    backend/data/

  To back up your data, copy this
  entire folder.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FAQ (Troubleshooting)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Q: Running start.sh gives "Permission denied"

  A: Grant execute permissions:
     chmod +x start.sh stop.sh

  ─────────────────────

  Q: "Port is already in use" error appears

  A: Another program may be using
     the same port (8000).
     Change PORT in config.env
     to a different number (e.g. 8080).

     To check which process is using it:
       ss -tlnp | grep :8000
     or:
       lsof -i :8000

  ─────────────────────

  Q: Browser does not open automatically

  A: Enter http://127.0.0.1:8000
     directly in your browser's address bar.

     * If there is no desktop environment
       (e.g. SSH connection), the browser
       will not open automatically.

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

  A: Copy the entire backend/data/ folder
     and place it in the same location
     on the destination machine.

  ─────────────────────

  Q: Errors about "libssl", "libffi", etc.

  A: Install the required system libraries:

     sudo apt update
     sudo apt install -y libssl-dev libffi-dev

     * Package names may differ depending
       on your Linux distribution.


============================================
