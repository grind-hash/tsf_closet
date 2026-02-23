============================================
  TSF Closet (Linux)  ─  Update Guide
============================================

  Thank you for using TSF Closet.

  This file explains how to update
  from a previous version on Ubuntu/Linux.

  * If this is your first time,
    please read "README_linux_en.txt" instead.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Before Updating
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Before you begin, please do the following:

  1. Stop the game if it is running

     - Press Ctrl+C in the terminal, or
     - Run ./stop.sh from another terminal

  2. Back up your old folder

     Copy these two items to a safe location:

     - config.env
       (contains your API key and settings)

     - backend/data/ folder
       (contains save data and generated images)

     Example:
       cp config.env ~/backup/
       cp -r backend/data ~/backup/

     * With a backup, you can always restore
       your previous state if something goes wrong.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Update Steps
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Extract the new version's archive

     tar xzf tsf_closet_portable_vX.X.X_linux.tar.gz

     * Extract to a different location
       than the old folder
     * Do not use paths with non-ASCII
       characters (e.g. Japanese)
       Example: ~/games/tsf_closet_new/

  2. Copy "config.env" from the old folder
     to the new folder

     cp ~/old_folder/config.env ~/new_folder/

     If config.env already exists in the
     new folder, overwrite it.

  3. Copy the entire "backend/data/" folder
     from the old folder to the new folder

     cp -r ~/old_folder/backend/data ~/new_folder/backend/

     * If a data folder already exists,
       overwrite it.

  4. Grant execute permissions to the scripts

     chmod +x start.sh stop.sh

  5. Run start.sh in the new folder

     cd ~/new_folder
     ./start.sh

  6. If the game screen appears in your browser,
     the update is complete

     * If the browser does not open,
       go to http://127.0.0.1:8000


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  New Settings in config.env
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  New settings may be added to config.env
  with version updates.

  If you copy your old config.env as-is,
  new settings will use their default values,
  which is fine for most users.

  To review or change new settings:

  1. Compare the new folder's config.env
     (before overwriting) with your old one

     diff ~/old_folder/config.env ~/new_folder/config.env

  2. If there are entries only in the new file,
     add them to your old config.env as needed

  * See "Customizing Settings (Advanced)"
    in README_linux_en.txt for details on
    each setting.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Changing the Language
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  This game supports Japanese and English.
  To switch languages, click the ⚙ (gear)
  icon at the top right of the game screen
  and select your preferred language in the
  "言語" (Language) section.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Release Notes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  For detailed changelogs and new features,
  please refer to the GitHub Releases page:

    https://github.com/grind-hash/tsf_closet/releases


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Troubleshooting
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Q: The game won't start after updating

  A: Check the following:
     - Did you extract the archive first?
     - Did you copy config.env correctly?
     - Does start.sh have execute permissions?
       chmod +x start.sh

  ─────────────────────

  Q: Save data is missing after updating

  A: Make sure you copied the backend/data/
     folder. You can restore it from your
     backup by copying the data folder into
     the new folder's backend/ directory.

     cp -r ~/backup/data ~/new_folder/backend/

  ─────────────────────

  Q: Image generation errors after updating

  A: Check the following:
     - Is NOVELAI_API_KEY set correctly
       in config.env?
     - Is your NovelAI subscription active?

  ─────────────────────

  Q: I want to go back to the old version

  A: Simply use the old folder you backed up.
     Run start.sh from the old folder.


============================================
