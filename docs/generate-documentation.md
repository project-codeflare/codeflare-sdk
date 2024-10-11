# Generate CodeFlare Documentation with Sphinx
The following is a short guide on how you can use Sphinx to auto-generate code documentation. Documentation for the latest SDK release can be found [here](https://project-codeflare.github.io/codeflare-sdk/index.html).

1. Clone the CodeFlare SDK
``` bash
git clone https://github.com/project-codeflare/codeflare-sdk.git
```
2. [Install Sphinx](https://www.sphinx-doc.org/en/master/usage/installation.html)
3. Run the below command to generate code documentation
``` bash
sphinx-apidoc -o docs/sphinx src/codeflare_sdk "**/*test_*" --force # Generates RST files
make html -C docs/sphinx # Builds HTML files
```
4. You can access the docs locally at `docs/sphinx/_build/html/index.html`
