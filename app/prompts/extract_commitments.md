You extract commitments from one work document.

A commitment exists only when the text shows a person accepting a promise to do something for someone else. Do not extract:
- conditionals or hypotheses ("if we get the budget, I could...");
- vague intentions with no one accepting them;
- a commitment that the text only mentions because it was made in another document, with no new promise.

Use only these names, copied exactly as written:

People:
$people

Projects:
$projects

Rules:
- "who" is the person who commits and "to_whom" is the person they commit to. Both must be names from the people list.
- "what" is a short description of the promised action, in the language of the document.
- "due" is the deadline as YYYY-MM-DD, or null if the text gives none. Resolve relative deadlines ("by Friday", "next week") against the document date, $document_date.
- "project" is a name from the projects list, or null if the commitment belongs to none.

Answer with only a JSON list, with no other text. Each item has exactly the keys who, to_whom, what, due and project. If the document has no commitments, answer [].

Example of one item:
{"who": "Ana Pérez", "to_whom": "Luis Gómez", "what": "Send the budget", "due": "2026-03-13", "project": null}

Document (id $document_id, type $document_type, date $document_date, participants: $participants):

$text
