# kicad_releaser

Automatically generates nice release artefacts on Github pages for kicad project.
Example at https://m0wut.github.io/Master-Timing-Reference/ 


# Installation

To use:

* Enable Github Actions as source for Github pages
1) Open Github repo on github
2) Setting, Pages, Build and deployment
3) Set Source to "GitHub Actions"

* Copy the `github` folder into your Kicad repo as `.github`. e.g. the `main.yml` should end up in `<top level git repo>/.github/workflows/main.yml`. Deliberately not done here as that'll cause the Github runner to run on this repo!

* Don't worry about the rest of the source code, it'll be cloned automatically through the Github runner.