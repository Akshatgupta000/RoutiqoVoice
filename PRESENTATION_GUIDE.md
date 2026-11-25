# Presentation guide

Use this as a speaking script. Say what the prototype actually does. If Gemini is down, say you are in demo mode and show that scoring and saving still work.

## 1. Thirty-second introduction

"This is Routiqo AI Sales Agent. Routiqo is a fleet dispatch and route optimization product. This assistant is the first sales conversation: it listens to a logistics customer, explains only what the product notes say, collects fleet size and the operational problem, scores the lead with fixed rules, saves it, and writes a call summary with the next step for a human salesperson. Speech recognition uses the browser's Web Speech API; browser support varies, and this is not a phone call."

## 2. Thirty-second business problem

"A salesperson currently has to explain dispatch software, discover whether the fleet is large enough to care, and remember to book a demo. That is slow and the notes get lost. This page runs that first pass and leaves a scored lead a person can follow up on. It does not replace the sales team, and it does not book the meeting by itself."

## 3. Forty-five-second architecture

"The customer talks into the browser. The browser keeps finalized speech separate from interim words and sends the complete finalized transcript to FastAPI when listening stops. It sends recent turns so the server can answer in context without storing the chat. A small keyword search picks sections from a markdown knowledge file. Those sections plus the sales rules go to Gemini. The reply comes back and the browser speaks it. When I save, Python adds the score, SQLite stores one lead row, and a summary endpoint writes the call notes. If Gemini fails, the same page uses a scripted reply and a template summary, and the screen says demo mode."

## 4. Two-minute live demo

1. Show the header: API connected, and either Demo mode or the Gemini model name. Say which one you are in.
2. Point at the stages: Listen, Reply, Qualify, Save lead.
3. Choose English (India) or English (US), then click **Start Listening** and allow microphone access. If browser recognition is unavailable, type the lines instead. Brave support is not guaranteed.
4. Send, one line at a time:
   - Hi, I am Priya Shah from Northline Logistics.
   - We have 35 vehicles.
   - We struggle with manual route planning and late deliveries.
   - My email is priya@northline.example and yes, I would like a product demo.
5. While the replies arrive, point out: one question at a time, the form filling in, and "Demo requested" with the note that this is not a calendar booking.
6. Ask: How does Routiqo optimize routes? The answer should mention techniques from the knowledge file, such as nearest-neighbor, 2-opt, or OSRM. If you ask about SAP or pricing, the assistant should defer to the sales team.
7. Click **Save lead and summarize**.
8. Read the score: 30 vehicles, 30 problem, 25 demo, 15 email, total 100, Qualified. Next action: schedule a product demonstration with the sales team.
9. Show the new row. Click **Refresh**. Optional: restart `./run.sh` and refresh the page. The row remains. The chat does not, unless this browser tab still has it.

If the microphone fails, type the same lines. Say that out loud so it looks intentional.

## 5. Scalability

"Today this is one FastAPI process and a SQLite file on my laptop. That is correct for a demo with one operator. To serve a sales team I would put several stateless API instances behind a load balancer, move leads to PostgreSQL, keep live call state in Redis with an expiry, and run summaries on a worker queue. Real phone calls need a telephony provider. Browser speech cannot dial a number.

100,000 registered users means 100,000 stored accounts, mostly idle. 100,000 simultaneous voice calls means 100,000 live audio sessions, each needing speech services and a model call. Those are different problems. This project does not claim either capacity."

## 6. Security

"The API key is only in `.env`, which is gitignored. SQLite queries use placeholders. Pydantic checks the JSON. The app sends finalized recognized text, not interim text, to the backend. The browser's speech service may handle microphone audio; check browser privacy behavior. I do not store the transcript permanently. There is no password because this server is for a local demonstration. Before production I would add login, HTTPS, a secret manager, rate limits, and a rule for how long lead data is kept."

## 7. Commercial feasibility

"The valuable part is not the chatbot window. It is a repeatable first call: qualify fleet size, problem, and demo interest, then hand a scored lead to a person. A company could use it on the website or, later, on real phone numbers. Cost is mainly the Gemini requests per conversation, which stay small because history is capped and answers are short. I would not sell the current build as a call center. Calendar booking, CRM sync, and telephony are the gaps between this demo and a product a logistics company would pay for. I am not claiming a revenue number or a performance benchmark."

## 8. Likely questions and short answers

**Why FastAPI?**  
It is a small Python web framework with automatic request checks through Pydantic and a built-in docs page. I can explain every endpoint. I did not need a larger framework for one page and six routes.

**Why Gemini?**  
The brief allows the Gemini API as the model provider. The official `google-genai` SDK sends the system instruction, the recent turns, and the knowledge snippets. The model name is an environment variable, so I can change it without rewriting the app.

**What is STT?**  
Speech-to-text. The browser `SpeechRecognition` API turns speech into text. The app shows interim words separately and sends only finalized transcript text to `/api/chat` after I stop listening. Browser support and network service availability vary.

**What is TTS?**  
Text-to-speech. `speechSynthesis` reads the assistant reply aloud after it arrives. When speaking finishes, the page can listen again.

**How does conversation memory work?**  
The server does not keep a session. The page stores the messages and sends the latest ones with each new line. The agent uses up to 12 of those turns and also lists facts it already extracted, so it tries not to ask the same question twice. Refreshing the tab can restore the chat from session storage. A new conversation clears it. Leads in SQLite are separate.

**How does knowledge retrieval work?**  
I split the markdown file into sections. I score each section by shared words with the customer message. Heading words count more. The best sections are copied into the prompt. That is keyword overlap, not embeddings and not a vector database. If nothing covers the question, the assistant says the sales team can clarify it in a demo.

**How is a lead qualified?**  
Python adds points: 30 for 10 or more vehicles, 30 for a stated problem, 25 for a demo request, 15 for an email. 70 and above is Qualified, 40 to 69 is Potential, below 40 is Not Qualified. The example in the demo is 35 vehicles, a routing problem, a demo request, and an email, which is 100. The model does not choose the score.

**Why SQLite?**  
It is a file. The app creates the table on startup. No separate database server is required for a laptop demo. Parameterized inserts keep customer text from changing the SQL. For many concurrent writers I would move to PostgreSQL. The scoring rules would stay the same.

**How would you scale this?**  
Stateless API instances behind a load balancer, PostgreSQL for leads, Redis for temporary conversation state, workers for summaries, and a telephony vendor for real calls. See the difference between registered users and simultaneous calls in the scalability answer above.

**How would you add real telephone calling?**  
I would connect a telephony provider that can receive a phone call, stream audio, and return transcripts. My `/api/chat` endpoint could stay, because it already accepts text. I would not describe the current microphone button as a phone system.

**How would you integrate a CRM?**  
After a lead is saved, a worker would send the company, contact, score, and summary to the CRM's API. I would store the CRM id on the lead. I have not built that, so the source of truth today is the SQLite row.

**How would you protect customer data?**  
Keep the demo local. For a real deployment: HTTPS, authentication, authorization, encrypted secrets, least-privilege database access, retention limits, and no API keys in logs. Do not store raw audio unless there is a clear reason and consent.

**What happens if the AI API fails?**  
Chat catches the error, logs a redacted message, and returns a demo-mode reply with a notice. Summary falls back to a template built from the form. The lead can still be scored and saved. The page never labels that reply as Gemini.

**Why not LangChain or a multi-agent setup?**  
The task is one sales conversation, one knowledge file, and one score. A single prompt is easier to explain and easier to debug in an interview. Extra agent frameworks would hide that flow.

**Does "Demo requested" mean the meeting is booked?**  
No. It means the customer asked for a demonstration and the sales team should make contact. There is no calendar integration. Booking would be a future enhancement, and only after a scheduling system confirms the slot.
