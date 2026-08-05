# English GUI publication build

The publication repository uses English for every user-visible desktop label and message. The scientific core (`core/`, profiles, scanner, classifier, exporter, database schemas, and rule expressions) is unchanged from the validated v0.4.1 core.

The previously produced Windows ZIP used Chinese interface labels and must **not** be uploaded as the publication binary. Rebuild the Windows package from this repository, run the strict test suite, run the packaged GUI acceptance workflow, and regenerate the GUI screenshots before public release.

A publication figure must use screenshots captured from the rebuilt executable. A translated or manually redrawn screenshot is not acceptable evidence.
