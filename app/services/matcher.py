from collections.abc import Iterable


def matching_keywords(title: str, body: str, keywords: Iterable[str]) -> set[str]:
    """Return keywords that occur in either field, ignoring case."""
    title, body = title.casefold(), body.casefold()
    return {
        keyword
        for keyword in keywords
        if keyword and (keyword.casefold() in title or keyword.casefold() in body)
    }
