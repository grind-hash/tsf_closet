"""API リクエスト / レスポンスの Pydantic モデル。

ドメイン別のモジュール（session / play / conversation / parameters / characters /
gallery / novelai / common）から直接 import する。内部状態の dataclass は
`gateway/models.py` に置く。
"""
