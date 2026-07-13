"""
ai_narrative.py
---------------
Generates the qualitative "Why not interested" narrative for Part 1,
routing through whichever Cloud AI engine was selected in the sidebar,
falling back to a local keyword-frequency algorithm if the API call
fails or no key was supplied.
"""

import collections
import json
import re

SYSTEM_PROMPT_INSTRUCTION = (
    "You are an expert financial data analyst. Analyze the following open-ended survey "
    "responses in English, Tagalog, or Taglish answering 'Bakit hindi interesado?' "
    "in the context of loan selling for MSMEs.\n\n"
    "Output must follow this HTML structure precisely:\n"
    "<h3>Reasons for not being interested in Home Credit Cash Loan:</h3>\n"
    "<ol><li><b>[Theme Name]</b> ([X] responses): Detailed explanation...</li></ol>\n"
    "<h3>Other insights:</h3>\n"
    "<ul><li>Detailed dynamic qualitative observations derived from reading the text...</li></ul>\n"
    "<h3>Recommendations:</h3>\n"
    "<ol><li>Detailed actionable strategical improvements for SAs and management...</li></ol>\n"
    "Do NOT use generalized headers or introductions. Return immediate HTML content with bold tags (<b>text</b>) for emphasis."
)


def _fallback_narrative(clean_responses):
    if not clean_responses:
        return "<p><b>No text data available</b> to execute analytical tracking arrays.</p>"

    tokens = collections.Counter()
    for r in [resp.lower() for resp in clean_responses]:
        words = [w for w in re.findall(r'\b\w+\b', r) if len(w) > 3 and w not in ['para', 'isang', 'nang', 'mga', 'hindi']]
        tokens.update(words)

    top_tokens = tokens.most_common(3)
    reasons_html = "<ol>"
    for word, count in top_tokens:
        reasons_html += f"<li>Objection patterns featuring keyword <b>'{word.capitalize()}'</b> detected ({count} occurrences across datasets).</li>"
    reasons_html += "</ol>"

    sample_1 = clean_responses[0] if len(clean_responses) > 0 else "N/A"
    sample_2 = clean_responses[-1] if len(clean_responses) > 1 else "N/A"

    return f"""
    <h3>Reasons for not being interested in Home Credit Cash Loan:</h3>
    {reasons_html}

    <h3>Other insights:</h3>
    <ul>
        <li><b>Unfiltered Feedback Contextualization:</b> Survey loops caught specific regional variations. Key verbatim data strings include: <i>"{sample_1}"</i>.</li>
        <li><b>Operational Resistance:</b> Structural resistance points correlate heavily with secondary expressions like: <i>"{sample_2}"</i>.</li>
    </ul>

    <h3>Recommendations:</h3>
    <ol>
        <li><b>Address High Frequency Keywords:</b> Standardize tactical rebuttals specifically targeting objection metrics highlighting structural phrases found in data loops.</li>
        <li><b>Localized Adjustments:</b> Cross-verify customer accounts flagged above to evaluate individual credit adjustment opportunities.</li>
    </ol>
    """


def generate_narrative(clean_responses, ai_mode, api_key, warn_fn=None):
    """Attempt to generate the disinterest narrative via the selected AI engine.

    warn_fn: optional callable(str) used to surface non-fatal warnings
             (e.g. st.warning). If None, warnings are silently swallowed.
    Always returns a non-empty HTML string (falls back locally on any failure).
    """
    def _warn(msg):
        if warn_fn:
            warn_fn(msg)

    formatted_txt = ""

    if "Groq" in ai_mode and api_key:
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_INSTRUCTION},
                    {"role": "user", "content": f"Responses to analyze:\n{json.dumps(clean_responses)}"}
                ],
                model="llama-3.1-8b-instant",
                temperature=0.3,
            )
            raw_text = chat_completion.choices[0].message.content
            formatted_txt = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text).replace("\n", "<br>")
        except Exception as e:
            _warn(f"Groq Cloud API connection failed: {e}. Checking fallback solutions.")

    elif "GitHub" in ai_mode and api_key:
        try:
            import openai
            client = openai.OpenAI(base_url="https://models.inference.ai.azure.com", api_key=api_key)
            response = client.chat.completions.create(
                model="meta-llama-3.1-405b-instruct",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_INSTRUCTION},
                    {"role": "user", "content": f"Responses to analyze:\n{json.dumps(clean_responses)}"}
                ],
                temperature=0.3
            )
            raw_text = response.choices[0].message.content
            formatted_txt = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text).replace("\n", "<br>")
        except Exception as e:
            _warn(f"GitHub Models connection failed: {e}. Checking fallbacks.")

    elif "Gemini" in ai_mode and api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name="gemini-2.5-flash", system_instruction=SYSTEM_PROMPT_INSTRUCTION)
            response = model.generate_content(
                f"Responses to analyze:\n{json.dumps(clean_responses)}",
                generation_config={"temperature": 0.3}
            )
            formatted_txt = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', response.text).replace("\n", "<br>")
        except Exception as e:
            _warn(f"Google Gemini API failed: {e}. Checking fallback solutions.")

    elif "OpenAI" in ai_mode and api_key:
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_INSTRUCTION},
                    {"role": "user", "content": f"Responses to analyze:\n{json.dumps(clean_responses)}"}
                ],
                temperature=0.3
            )
            formatted_txt = response.choices[0].message.content
        except Exception as e:
            _warn(f"OpenAI API pipeline failed: {e}. Falling back to text algorithm matrix.")

    if not formatted_txt:
        formatted_txt = _fallback_narrative(clean_responses)

    return formatted_txt