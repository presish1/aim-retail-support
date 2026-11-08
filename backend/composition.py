"""Grounded model language with locked transactional fact blocks and a deterministic fallback.

These checks reduce specific unsupported claims; they are not an entailment proof.
"""

import re

PLACEHOLDER = re.compile(r"\{\{fact:([a-z_]+)\}\}")
ALLOWED = {
    "status",
    "eta",
    "tracking",
    "payment",
    "total",
    "items",
    "destination",
    "return_status",
    "catalog",
    "policy_window",
    "return_conditions",
}


def compile_reply(template, facts, required=(), guide_ids=(), available_guides=()):
    if not isinstance(template, str) or not 15 <= len(template) <= 1600:
        return None, "No usable model reply"
    referenced = PLACEHOLDER.findall(template)
    if set(referenced) - ALLOWED or any(k not in facts for k in referenced):
        return None, "Unknown or unavailable fact reference"
    if not set(required) <= set(referenced):
        return None, "Required answer facts omitted"
    for line in template.splitlines():
        if PLACEHOLDER.search(line) and PLACEHOLDER.sub("", line).strip(" \t.*:"):
            return None, "Complete fact block embedded inside a sentence"
    if set(guide_ids) - set(available_guides):
        return None, "Unretrieved guidance reference"
    prose = PLACEHOLDER.sub("", template)
    if (
        "=>" in prose
        or "[verified value]" in prose
        or re.search(
            r"\b(?:offer to|never promise|response.constraints|fact blocks|the customer|use the locked|not configured here|this system doesn't provide)\b",
            prose,
            re.I,
        )
    ):
        return None, "Internal response instructions or implementation language"
    if (
        "{{" in prose
        or "}}" in prose
        or re.search(
            r"\d|₹|\$|https?://|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", prose, re.I
        )
    ):
        return None, "Unprotected value, URL or identifier"
    # Status/eligibility/financial confirmations belong to locked facts, never model prose.
    if re.search(
        r"\b(delivered|cancelled|canceled|refunded|approved|ineligible|eligible|in transit|on its way|being prepared|paid|unpaid|processing|final.sale)\b",
        prose,
        re.I,
    ):
        return None, "Unprotected transactional claim"
    if re.search(
        r"\b(?:i|we|the store|your).{0,30}(?:have |has |just |already )?(?:booked|reserved|issued|created|saved|changed|processed|credited)\b",
        prose,
        re.I,
    ):
        return None, "Unconfirmed action claim"
    if re.search(
        r"\b(?:I'll|I will|we will).{0,25}(?:let you know|notify|update you).{0,40}(?:as soon|immediately|automatically)",
        prose,
        re.I,
    ):
        return None, "Unconfirmed proactive notification promise"
    # Evaluate positive promises by clause so a clear inability to guarantee isn't a guarantee.
    # Splitting contrasts/conjunctions keeps 'can't promise, but it will arrive' rejectable.
    promise_prose = " ".join(
        clause
        for clause in re.split(r"[.;!?\n]|\b(?:but|however|and)\b", prose, flags=re.I)
        if not re.search(
            r"\b(?:can't|cannot|won't|don't|do not|unable to)\s+(?:promise|guarantee|confirm|say|tell|know)\b",
            clause,
            re.I,
        )
    )
    if re.search(
        r"\b(?:will|guarantee|definitely|certainly).{0,45}\b(?:arrive|reach|receive|refund|deliver|bank|credit|approve)\b|\b(?:free (?:return|pickup|shipping)|no charge|waived|(?:in|is) stock|bank.{0,20}(?:soon|shortly)|(?:few|couple|several|two|three|five|seven|ten) (?:business )?days)\b",
        promise_prose,
        re.I,
    ):
        return None, "Unsupported promise or inventory claim"
    if re.search(
        r"\b(?:parcel|order|package|delay).{0,35}(?:because|due to)|because.{0,35}(?:weather|traffic|warehouse|customs|courier)",
        prose,
        re.I,
    ):
        return None, "Unsupported causal explanation"
    if re.search(
        r"\b(?:today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        prose,
        re.I,
    ):
        return None, "Unprotected relative date"
    if re.search(r"\b(?:pickup|return|shipping).{0,15}\bfree\b", prose, re.I):
        return None, "Unconfirmed fee claim"
    # Don't ask for financial secrets, even if user input tried to instruct it.
    request_prose = re.sub(
        r"(?:don't|do not|never|avoid)\s+(?:send|share|give|provide).{0,45}(?:passwords?|bank otps?|card numbers?|cvv)",
        "",
        prose,
        flags=re.I,
    )
    if re.search(
        r"(?:send|share|give|provide).{0,35}(?:password|bank otp|card number|cvv)",
        request_prose,
        re.I,
    ):
        return None, "Sensitive-data request"
    rendered = PLACEHOLDER.sub(lambda m: facts[m[1]], template).strip()
    return rendered, None
