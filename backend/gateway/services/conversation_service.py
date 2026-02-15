from __future__ import annotations

from .conversation import is_response_language_valid


class ConversationService:
    async def generate_with_language_retry(
        self,
        llm_service,
        system_prompt: str,
        user_prompt: str,
        language: str,
    ) -> str | None:
        current_user_prompt = user_prompt
        for _ in range(2):
            result = await llm_service.generate_feeling(
                system_prompt=system_prompt,
                user_prompt=current_user_prompt,
            )
            candidate = result.content
            if is_response_language_valid(candidate, language):
                return candidate
            current_user_prompt = f"{user_prompt}\n\nIMPORTANT: Respond in {'English only' if language == 'en' else 'Japanese only'}."
        return None


conversation_service = ConversationService()
