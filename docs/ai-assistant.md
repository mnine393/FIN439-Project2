# Ask Compass: the in-app AI assistant

**What it is.** A chat panel on every page (bottom-right button, or Ctrl+K). You can ask about what is on
the screen ("Why is my chance 41%?"), ask a what-if question ("What if I add $200 a month?"), or describe a
portfolio in words ("something like Buffett's, but safer, for $100,000").

**How it works.**
1. Claude (model `claude-opus-5-5`) reads the question, along with short facts about the page you are looking at.
2. It chooses which Compass tools to run. The tools are the engine's own functions: build a personal plan,
   analyze a portfolio, compare two portfolios, test past forecast accuracy, look up a ticker, read a 13F
   filing, and run the Buffett and Burry stock screens.
3. The engine computes every number. Claude only explains the results.
4. Code then checks each number in the answer against the numbers the tools and the page printed. The chat
   shows "Every number checked against the Compass engine", or it lists any number it could not verify.

**Why it is built this way.** A language model can state a wrong number with confidence. Here the model
never does the arithmetic, and a separate check catches any number it makes up. This is the same rule
as the committee memos: code computes, the AI explains, and code checks.

**Turning it on.** Install the package with `pip install anthropic`. Then set the key on your own computer
only. Never put it in the repository:

```powershell
$env:ANTHROPIC_API_KEY = "your key"
python run.py
```

**Without a key: the built-in mode (free).** The chat still works, with no AI service and no cost. Plain
rules in `assistant_offline.py` recognize common questions and run the same engine tools, and the same
number check runs afterwards. It handles these questions:
- what-ifs about your plan ("What if I add $200 a month?", "What if my goal is $800,000?", "What if I have 25 years?")
- a portfolio typed into the chat ("Analyze 50000 VTI, 30000 VXUS, 20000 BND" or "60% VT 40% BND on $250,000")
- on the Analyze page: "Make this safer", "Which holding adds the most risk?", "How did it do in 2008?"
- "What does Buffett own?" and "What does Burry own?"
- definitions of the glossary terms
- every "Explain this" button

Anything else gets a list of what it can do. With a key, the same panel switches to the full AI automatically.

**Limits.** The assistant gives education, not investment advice. It only knows what its tools return and
what the page shows. Answers can still be worded badly or miss the point even when every number is checked.
Conversations are kept in memory on your own computer and are cleared when Compass restarts.

**Files.** `assistant.py` contains the tool definitions, the chat loop and the number check. Its tests are in
`tests/test_assistant.py` and use a fake Claude client, so no key or network is needed. The chat panel is in
`web/js/assistant.js`.
