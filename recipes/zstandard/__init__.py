from pythonforandroid.recipe import PythonRecipe


class ZstandardRecipe(PythonRecipe):
    version = '0.22.0'
    url = 'https://github.com/indygreg/python-zstandard/archive/refs/tags/0.22.0.tar.gz'
    depends = ['setuptools']
    site_packages_name = 'zstandard'
    call_hostpython_via_targetpython = False


recipe = ZstandardRecipe()
