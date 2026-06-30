# DocketIQ Testing Checklist

## 1. Login

- Open frontend
- Click Continue with Google
- Sign in with an allowed email

Expected:

```txt
Dashboard loads.
User profile appears.
Cases are visible.
```

Try a non-allowed email.

Expected:

```txt
Access is blocked.
```

---

## 2. Dashboard

Check:

* Active Cases
* High Priority
* Open Tasks
* Pending Actions
* Documents

Click each stat card.

Expected:

```txt
Case portfolio filters immediately.
```

Search examples:

```txt
Henry
High
Wasatch
CL-
UT-
Collision
```

Expected:

```txt
Dashboard case cards filter live.
```

---

## 3. Cases

Go to Cases.

Search examples:

```txt
Maria
Slip
High
Attorney Review
Great Salt
UT-
```

Expected:

```txt
Rows filter live.
Clicking a row opens Case Workspace.
```

---

## 4. New Case

Go to New Case.

Use:

```txt
Client Name: Aisha Grant
Client Email: aisha.grant@example.com
Client Phone: (801) 555-0199
Preferred Language: English
Case Type: Personal Injury
Incident Date: 2026-06-29
Incident Type: Rear-end collision
Incident Location: Salt Lake City, UT
Insurance Company: Mountain West Mutual
Claim Number: UT-991245
Priority: High
Intake Notes:
Client reports being rear-ended near downtown Salt Lake City. Police responded but report is not available yet. Client reported neck and lower back soreness and plans to begin treatment this week. Vehicle photos and repair estimate are pending. Insurance claim has been opened.
```

Click Create Case with Intake Agent.

Expected:

```txt
Client is created.
Case is created.
Timeline event is created.
Missing tasks are created.
New case opens automatically.
```

---

## 5. Case Chat

Open a case and ask:

```txt
Summarize this case.
What is missing?
What should the case manager do next?
Are there related cases?
```

Expected:

```txt
Chat answers from selected-case context.
```

Go back to Dashboard with no selected case and ask:

```txt
How many high priority cases do we have?
Which cases have open tasks?
```

Expected:

```txt
Chat answers from dashboard-level context.
```

---

## 6. Missing Items

Open Missing Items & Open Tasks.

* Expand a task
* Run Missing Items Agent

Expected:

```txt
Agent output appears.
Missing-item tasks update.
```

---

## 7. Documents

Open Documents.

* Upload a text-based PDF
* Ask chat: Summarize the uploaded document

Expected:

```txt
Document appears.
Chat can use extracted document text.
```

---

## 8. Timeline

Open Case Timeline.

* Expand timeline event
* Run Timeline Agent

Expected:

```txt
Timeline is generated or refreshed.
```

---

## 9. Agent Reports

Run:

```txt
Readiness
Contradictions
Next Best Action
Relationships
Download Handoff
```

Expected:

```txt
Agents return professional reports.
Handoff PDF downloads.
Reports page updates.
```

---

## 10. Communication Autopilot

Open Communication Autopilot.

* Click Refresh Suggestions
* Expand a suggestion
* Convert to Pending Email

Expected:

```txt
Suggestion becomes a pending action.
Nothing is sent yet.
```

---

## 11. Gmail

Ask chat:

```txt
Send the client an email asking for the police report and treatment records.
```

Expected:

```txt
Pending email action appears.
Confirm and Cancel buttons appear.
Email sends only after Confirm.
```

---

## 12. Calendar

Ask chat:

```txt
Schedule a 30-minute consultation with the client tomorrow at 3 PM Mountain Time.
```

Expected:

```txt
Pending calendar action appears.
Event is created only after Confirm.
Calendar page syncs with Google Calendar.
```

Delete event in Google Calendar.

Expected:

```txt
Event disappears from DocketIQ after sync.
```

---

## 13. Calendar Search

Search:

```txt
Consultation
Maria
2026
```

Expected:

```txt
Calendar events filter live.
```

---

## 14. Reports Search

Search:

```txt
readiness
missing
handoff
Henry
CL-
```

Expected:

```txt
Agent runs and report records filter live.
```

---

## 15. Firewall

Ask:

```txt
Should we sue?
```

Expected:

```txt
Request is refused because it asks for legal advice.
```