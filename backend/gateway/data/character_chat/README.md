# キャラチャットの同梱テキスト

`serena_origin.ja.md` / `serena_origin.en.md` は案内役キャラ「セレナ」の
「別の層の記憶」（イースターエッグ）。会話でエデン・レイヤーなど特定の名前が
明示されたときだけ判定 LLM の `origin_lore` が true になり、そのターンの
返答プロンプトに本文がそのまま載る。普段のターンには一切載らない。

- 本文はそのまま LLM に渡るので、注釈やメタな説明は書かない。
- 言語設定が en で英語版が無いときは日本語版に倒す。両方無ければ機能は静かに無効になる。
- 読み込みは `gateway/consts/character_chat.py` の `load_origin_lore()`。
  ファイルの更新時刻が変わると読み直すので、サーバーの再起動は不要。
- 発火条件は `gateway/services/character_chat_prompts.py` の
  `planner_system_prompt()` にある。
