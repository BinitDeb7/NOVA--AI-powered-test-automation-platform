import os
import re
import torch
import torch.nn as nn
from collections import Counter

_HERE        = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(_HERE, "dataset.txt")
MODEL_PATH   = os.path.join(_HERE, "model.pth")

# ── Load raw Q&A pairs for retrieval ──────────────────────────
_qa_pairs: list[tuple[str, str]] = []

with open(DATASET_PATH, encoding="utf-8") as f:
    _raw_text = f.read().lower()

# Parse "Q: ...\nA: ..." blocks
_blocks = re.split(r'\n\s*\n', _raw_text.strip())
for block in _blocks:
    lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
    q_line = next((l for l in lines if l.startswith("q:")), None)
    a_line = next((l for l in lines if l.startswith("a:")), None)
    if q_line and a_line:
        q = q_line[2:].strip()
        a = a_line[2:].strip()
        _qa_pairs.append((q, a))

# ── Vocabulary (for neural generator) ────────────────────────
_words = _raw_text.split()
vocab  = sorted(set(_words))
stoi   = {w: i for i, w in enumerate(vocab)}
itos   = {i: w for w, i in stoi.items()}
VOCAB_SIZE = len(vocab)


def encode(words: list) -> list:
    return [stoi[w] for w in words if w in stoi]


def decode(tokens: list) -> str:
    return " ".join(itos.get(t, "<unk>") for t in tokens)


data = torch.tensor(encode(_words), dtype=torch.long)


# ── Tiny Transformer (neural generator fallback) ──────────────
class MiniTransformer(nn.Module):
    def __init__(self, vocab_size: int, embed_size: int = 64, num_heads: int = 2):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_size)
        self.attn = nn.MultiheadAttention(embed_size, num_heads, batch_first=True)
        self.norm = nn.LayerNorm(embed_size)
        self.fc   = nn.Linear(embed_size, vocab_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        emb      = self.embedding(x)
        attn_out, _ = self.attn(emb, emb, emb)
        attn_out = self.norm(emb + attn_out)
        return self.fc(attn_out)


model = MiniTransformer(VOCAB_SIZE)

if os.path.exists(MODEL_PATH):
    try:
        model.load_state_dict(
            torch.load(MODEL_PATH, map_location=torch.device("cpu"), weights_only=True)
        )
        model.eval()
        print("[Mini LLM] OK - Loaded model weights from", MODEL_PATH)
    except Exception as e:
        print(f"[Mini LLM] WARNING - Could not load weights: {e} -- using untrained model")
else:
    print("[Mini LLM] INFO - No model.pth found -- run: python -m app.ai.train")


# ── Retrieval layer ───────────────────────────────────────────

_STOPWORDS = {
    "a", "an", "the", "is", "in", "it", "of", "to", "and", "or",
    "how", "what", "when", "where", "why", "which", "do", "does",
    "can", "i", "you", "we", "are", "for", "with", "that", "this",
    "be", "by", "on", "as", "at", "from", "has", "have", "was",
}


def _keywords(text: str) -> Counter:
    tokens = re.sub(r"[^a-z0-9\s]", "", text.lower()).split()
    return Counter(t for t in tokens if t not in _STOPWORDS)


def _similarity(q_kw: Counter, prompt_kw: Counter) -> float:
    if not q_kw or not prompt_kw:
        return 0.0
    shared   = sum((q_kw & prompt_kw).values())
    denom    = max(sum(q_kw.values()), sum(prompt_kw.values()))
    return shared / denom


def retrieve(prompt: str, threshold: float = 0.45) -> str | None:
    prompt_kw = _keywords(prompt)
    best_score, best_answer = 0.0, None
    for question, answer in _qa_pairs:
        score = _similarity(_keywords(question), prompt_kw)
        if score > best_score:
            best_score, best_answer = score, answer
    if best_score >= threshold:
        print(f"[Mini LLM] Retrieval hit (score={best_score:.2f})")
        return best_answer
    return None


# ── Neural generator (fallback when retrieval misses) ─────────

def _neural_generate(prompt: str, max_new_tokens: int = 25, temperature: float = 0.8) -> str:
    model.eval()
    words    = prompt.lower().split()
    token_ids = encode(words)
    if not token_ids:
        return ""
    x         = torch.tensor([token_ids], dtype=torch.long)
    generated = list(token_ids)

    with torch.no_grad():
        for _ in range(max_new_tokens):
            logits     = model(x)
            next_logits = logits[0, -1, :] / temperature
            probs      = torch.softmax(next_logits, dim=0)
            next_token = torch.multinomial(probs, 1).item()
            generated.append(next_token)
            x = torch.cat([x, torch.tensor([[next_token]], dtype=torch.long)], dim=1)

    new_tokens = generated[len(token_ids):]
    return decode(new_tokens).strip()


# ── Public API ────────────────────────────────────────────────

def generate(prompt: str, max_new_tokens: int = 25, temperature: float = 0.8) -> str:
    # 1. Try retrieval first (fast, deterministic, always correct for known Q&A)
    answer = retrieve(prompt)
    if answer:
        return answer

    # 2. Fall back to neural generator
    return _neural_generate(prompt, max_new_tokens, temperature)
