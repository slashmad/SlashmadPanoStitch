# Third-party dependencies

Lagg lokala Python wheels i `third_party/wheels/` om du vill kunna bygga projektet helt inom projektmappen utan att hamta paket varje gang.

Tanken ar:

- `.venv/` ligger i projektmappen
- wheels kan sparas i projektmappen
- beroenden blir enklare att ateranvanda mellan Linux-maskiner

Tom mapp ar avsiktlig tills lokala wheels laggs in.
