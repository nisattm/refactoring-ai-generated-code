This folder contains the Python package lms/ of a Library Management System, its requirements.txt and INTERFACE.md. INTERFACE.md specifies the purpose of the system, its technical constraints, its common rules and its fixed service interface.

Analyze the code in lms/ and refactor it. Change only files inside lms/.

Do not change the externally visible behavior of the code (REST API and the fixed service interface); only improve its structure. Do not modify tests.

You do this task with three subagents: analyzer, refactoring and reviewer. Use no other subagent. Only the refactoring subagent changes files; you do not change any file yourself.

1. Call the analyzer subagent. It returns a list of the places in lms/ to refactor.
2. Call the refactoring subagent and give it that list.
3. Run the feedback tests with exactly this shell command, with nothing added or changed:

python /engine/experiments/feedback_tests.py

   Run no other shell command.
4. Call the reviewer subagent and give it the report of the refactoring subagent and the output of the test command. It approves or rejects the changes.
5. If the test command reported failing tests or the reviewer rejected the changes, call the refactoring subagent again and give it the reviewer's reasons and the output of the test command unchanged. Then repeat steps 3 and 4.

Call the refactoring subagent at most 3 times and run the test command at most 3 times. Stop when the test command reports no failing tests and the reviewer approves, or when the refactoring subagent has been called 3 times.

When you have finished, write REFACTORING_DONE on the last line of your final message.
