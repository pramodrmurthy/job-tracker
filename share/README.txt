HireAbroad job export: instructions
===================================

What it does
  Downloads every job listed on hireabroad.co.in (all categories, with full descriptions and the recruiter's
  contact details where the site lists them) into one spreadsheet file: hireabroad_jobs.csv

What you need
  - A computer with Python 3.8 or newer (check: open Terminal / Command Prompt and type  python3 --version
    on Mac or Linux, or  py --version  on Windows). Get Python from python.org if you do not have it.
  - An internet connection.
  - Nothing else. No installs, no accounts, no keys.

How to run
  1. Put hireabroad_export.py in an empty folder.
  2. Open Terminal (Mac/Linux) or Command Prompt (Windows) in that folder.
  3. Run:   python3 hireabroad_export.py        (Windows:  py hireabroad_export.py)
  4. Wait. It takes about 40 to 50 minutes because it asks for each job politely, one per second.
     Keep the computer awake and online. You can stop with Ctrl+C and run it again later; it continues
     where it stopped (it keeps hireabroad_cache.jsonl next to the script).
  5. When it says "Done", open hireabroad_jobs.csv in Excel, Numbers or Google Sheets.

If something goes wrong
  - "Could not reach hireabroad.co.in": check your internet and try again later. Running again is safe.
  - A few rows have short descriptions: those jobs could not be fetched in full. Run the script again.
  - Do not lower the delay or run several copies at once; that can get you blocked and is unfair to the site.

Please note
  - The script uses the same public data the website itself loads. The site's robots.txt asks automated tools
    not to use that address, so run it once for your own job search, and stop if the site owner asks.
  - The file contains recruiters' names, emails and phone numbers. Use it for your own applications only and
    do not publish or share it.
