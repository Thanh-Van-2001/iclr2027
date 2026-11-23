Put each annotator's exported CSV here, unchanged: one file per annotator, any name ending in .csv.
Declare the annotator in ../../annotators.csv, then freeze the file:

    python aamas/human_validation_kits.py freeze --kit comparison_blind

After freezing, a raw file is never edited. Corrections go in ../adjudication.csv.
This folder holds no label yet.
