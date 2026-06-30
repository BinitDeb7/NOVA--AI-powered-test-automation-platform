import torch
import torch.nn as nn

from app.ai.mini_llm import model, data, VOCAB_SIZE, MODEL_PATH

STEPS = 2000
LEARNING_RATE = 1e-3
SEQ_LEN = 8
PRINT_EVERY = 200


def train():
    print("=" * 55)
    print("  Mini LLM Training -- Hybrid AI for TestVerse")
    print("=" * 55)
    print(f"  Vocab size   : {VOCAB_SIZE} words")
    print(f"  Dataset size : {len(data)} tokens")
    print(f"  Steps        : {STEPS}")
    print(f"  Context len  : {SEQ_LEN}")
    print("=" * 55)

    if len(data) < SEQ_LEN + 2:
        print("ERROR: Dataset too small. Add more sentences to dataset.txt")
        return

    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    loss_fn = nn.CrossEntropyLoss()

    model.train()

    for step in range(1, STEPS + 1):
        max_start = len(data) - SEQ_LEN - 1
        idx = torch.randint(0, max_start, (1,)).item()

        x = data[idx: idx + SEQ_LEN].unsqueeze(0)
        y = data[idx + 1: idx + SEQ_LEN + 1]

        logits = model(x)
        loss = loss_fn(logits.view(-1, VOCAB_SIZE), y)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if step % PRINT_EVERY == 0 or step == 1:
            print(f"  Step {step:>4}/{STEPS}  |  Loss: {loss.item():.4f}")

    torch.save(model.state_dict(), MODEL_PATH)
    print()
    print("Training complete! Model saved ->", MODEL_PATH)
    print("You can now run the Flask app: python run.py")


if __name__ == "__main__":
    train()
