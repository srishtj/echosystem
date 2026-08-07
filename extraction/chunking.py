import tiktoken

enc = tiktoken.get_encoding("cl100k_base")

def dynamic_chunks(text: str, max_tokens: int = 3000):
    words = text.split()
    chunks, current, current_tokens = [], [], 0
    for w in words:
        t = len(enc.encode(w + " "))
        if current_tokens + t > max_tokens:
            chunks.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(w)
        current_tokens += t
    if current:
        chunks.append(" ".join(current))
    return chunks
