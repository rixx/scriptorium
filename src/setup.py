from setuptools import setup

setup(
    name="scriptorium",
    author="Tobias Kunze",
    author_email="r@rixx.de",
    url="https://github.com/rixx/scriptorium",
    packages=["scriptorium"],
    # entry_points="""
    #     [console_scripts]
    #     scriptorium=???
    # """,
    install_requires=[
        "bs4",
        "django==4.1.*",
        "django_context_decorator==1.6.0",
        "django-formtools==2.3",
        "inquirer==2.6.*",
        "jinja2==2.11.*",
        "markdown==3.1.*",
        "markupsafe==2.0.1",
        "networkx==2.5.*",
        "pillow==8.4.*",
        "python-dateutil",
        "python-frontmatter==0.5.*",
        "requests",
        "scikit-learn",
        "smartypants==2.0.*",
        "tqdm",
        "unidecode==1.1.*",
        "whitenoise==6.2.*",
        "numpy<2.0",
        "pygal==3.0.*",
    ],
)
