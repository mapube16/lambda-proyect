"""
test_cobranza_queen.py — TDD tests for cobranza_queen.py (Plan 17-04).

Behavior spec:
- generate_cobranza_proposal(user_description, empresa_nombre) returns dict
- Keys: tono, frecuencia_dias, max_intentos, guion
- guion has 4 sub-keys: saludo, propuesta, objeciones, cierre
- Returns fallback dict (no raise) when OPENAI_API_KEY is missing
- max_intentos clamped to [1, 10]; frecuencia_dias clamped to [1, 3]
- empresa_nombre appears in fallback saludo
"""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def restore_openai_key():
    """Restore OPENAI_API_KEY after each test (some tests remove it)."""
    original = os.environ.get("OPENAI_API_KEY")
    yield
    if original is not None:
        os.environ["OPENAI_API_KEY"] = original
    else:
        os.environ.pop("OPENAI_API_KEY", None)


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestGenerateCobranzaProposal:
    """Tests for generate_cobranza_proposal()."""

    def test_import_succeeds(self):
        """Module and function are importable."""
        from cobranza.cobranza_queen import generate_cobranza_proposal  # noqa: F401
        assert callable(generate_cobranza_proposal)

    def test_fallback_returns_dict_on_missing_api_key(self):
        """With no OPENAI_API_KEY set, function returns fallback dict without raising."""
        from cobranza.cobranza_queen import generate_cobranza_proposal
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("OPENAI_API_KEY", None)
            result = run(generate_cobranza_proposal("cartera vencida 30 días", "Acme"))
        assert isinstance(result, dict)

    def test_fallback_has_required_top_level_keys(self):
        """Fallback dict has tono, frecuencia_dias, max_intentos, guion."""
        from cobranza.cobranza_queen import generate_cobranza_proposal
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        result = run(generate_cobranza_proposal("test", "Acme"))
        assert "tono" in result
        assert "frecuencia_dias" in result
        assert "max_intentos" in result
        assert "guion" in result

    def test_fallback_guion_has_four_keys(self):
        """Fallback guion dict has saludo, propuesta, objeciones, cierre."""
        from cobranza.cobranza_queen import generate_cobranza_proposal
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        result = run(generate_cobranza_proposal("test", "Acme"))
        guion = result["guion"]
        assert "saludo" in guion
        assert "propuesta" in guion
        assert "objeciones" in guion
        assert "cierre" in guion

    def test_fallback_saludo_contains_empresa_nombre(self):
        """Fallback saludo contains empresa_nombre."""
        from cobranza.cobranza_queen import generate_cobranza_proposal
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        result = run(generate_cobranza_proposal("test", "MiEmpresa"))
        assert "MiEmpresa" in result["guion"]["saludo"]

    def test_fallback_max_intentos_in_range(self):
        """Fallback max_intentos is between 1 and 10."""
        from cobranza.cobranza_queen import generate_cobranza_proposal
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        result = run(generate_cobranza_proposal("test", "Acme"))
        assert 1 <= result["max_intentos"] <= 10

    def test_fallback_frecuencia_dias_in_range(self):
        """Fallback frecuencia_dias is between 1 and 3."""
        from cobranza.cobranza_queen import generate_cobranza_proposal
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        result = run(generate_cobranza_proposal("test", "Acme"))
        assert 1 <= result["frecuencia_dias"] <= 3

    def test_openai_response_parsed_correctly(self):
        """With mocked OpenAI, returns parsed proposal dict."""
        from cobranza.cobranza_queen import generate_cobranza_proposal

        mock_response_content = '{"tono":"firme","frecuencia_dias":1,"max_intentos":7,"guion":{"saludo":"Hola","propuesta":"Deuda","objeciones":"Entiendo","cierre":"Gracias"}}'

        mock_choice = MagicMock()
        mock_choice.message.content = mock_response_content
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("cobranza.cobranza_queen.openai") as mock_openai:
            mock_openai.AsyncOpenAI.return_value = mock_client
            import os
            os.environ["OPENAI_API_KEY"] = "test-key"
            result = run(generate_cobranza_proposal("cartera 60 días", "Banco X"))
            os.environ.pop("OPENAI_API_KEY", None)

        assert result["tono"] == "firme"
        assert result["frecuencia_dias"] == 1
        assert result["max_intentos"] == 7
        assert result["guion"]["saludo"] == "Hola"

    def test_max_intentos_clamped_high(self):
        """max_intentos above 10 is clamped to 10."""
        from cobranza.cobranza_queen import generate_cobranza_proposal

        mock_response_content = '{"tono":"firme","frecuencia_dias":2,"max_intentos":99,"guion":{"saludo":"Hola","propuesta":"Deuda","objeciones":"Entiendo","cierre":"Gracias"}}'

        mock_choice = MagicMock()
        mock_choice.message.content = mock_response_content
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("cobranza.cobranza_queen.openai") as mock_openai:
            mock_openai.AsyncOpenAI.return_value = mock_client
            import os
            os.environ["OPENAI_API_KEY"] = "test-key"
            result = run(generate_cobranza_proposal("test", "Banco X"))
            os.environ.pop("OPENAI_API_KEY", None)

        assert result["max_intentos"] == 10

    def test_frecuencia_dias_clamped_high(self):
        """frecuencia_dias above 3 is clamped to 3."""
        from cobranza.cobranza_queen import generate_cobranza_proposal

        mock_response_content = '{"tono":"firme","frecuencia_dias":7,"max_intentos":5,"guion":{"saludo":"Hola","propuesta":"Deuda","objeciones":"Entiendo","cierre":"Gracias"}}'

        mock_choice = MagicMock()
        mock_choice.message.content = mock_response_content
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        with patch("cobranza.cobranza_queen.openai") as mock_openai:
            mock_openai.AsyncOpenAI.return_value = mock_client
            import os
            os.environ["OPENAI_API_KEY"] = "test-key"
            result = run(generate_cobranza_proposal("test", "Banco X"))
            os.environ.pop("OPENAI_API_KEY", None)

        assert result["frecuencia_dias"] == 3

    def test_exception_from_openai_returns_fallback(self):
        """Any exception from OpenAI returns fallback dict without raising."""
        from cobranza.cobranza_queen import generate_cobranza_proposal

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("network error"))

        with patch("cobranza.cobranza_queen.openai") as mock_openai:
            mock_openai.AsyncOpenAI.return_value = mock_client
            import os
            os.environ["OPENAI_API_KEY"] = "test-key"
            result = run(generate_cobranza_proposal("test", "Acme"))
            os.environ.pop("OPENAI_API_KEY", None)

        assert isinstance(result, dict)
        assert "tono" in result
        assert "guion" in result
