# Demo script (target: 2:30, hard limit 3:00)

Before recording: run `paperwork models`, set `NEBIUS_MODEL`, run `paperwork forget --all`, and make sure the letter's appeal date is still in the future (or edit the date in `demo/sample_letter.txt`).

| Time | On screen | Say |
|---|---|---|
| 0:00-0:20 | Title card, then `demo/sample_letter.txt` | "Official letters are hard to read, and missing a deadline can cost real money. This is a synthetic insurance letter. Paperwork Assistant explains it in plain language." |
| 0:20-0:50 | `paperwork explain demo/sample_letter.txt --hide "Ravi Kumar Sharma"` | "It runs NVIDIA Nemotron on Nebius Token Factory. Before anything is sent, emails, phone numbers, ID numbers and the name I passed are replaced with placeholders. The count shows how many were masked." |
| 0:50-1:25 | Scroll the output | "A plain summary, the amounts, what to do next, questions I could ask the insurer, and anything unclear. It does not give medical, legal or financial advice." |
| 1:25-1:50 | `paperwork deadlines --days 60` | "It remembered the appeal deadline in a local SQLite database. Close the app, come back next week, and the deadline is still there." |
| 1:50-2:15 | `paperwork ask "when is my appeal due?"` | "Follow-up questions are answered from my saved summaries. Names are still masked before the cloud call." |
| 2:15-2:30 | `paperwork forget --all`, then `paperwork deadlines` | "And I can delete everything with one command." |
| 2:30-2:45 | Closing card | "This is data minimisation, not anonymisation: Token Factory is a cloud service, and redaction can miss things. Open source under MIT. Thank you." |

Tips: keep the terminal font large, do one take of each command beforehand to warm up the model, and cut any waiting time in editing.
