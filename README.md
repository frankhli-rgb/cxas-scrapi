<div align="center">
  <h3 align="center">CX Agent Studio Scripting API (CXAS SCRAPI)</h3>
  <p align="center">
    A high-level scripting API for AI agent builders, developers, and maintainers.<br>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details open="open">
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#introduction">Introduction</a>
      <ul>
        <li><a href="#what-can-i-do-with-cxas-scrapi">What Can I Do with SCRAPI?</a></li>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#environment-setup">Environment Setup</a></li>
        <li><a href="#authentication">Authentication</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a>
    <li>
      <a href="#library-composition">Library Composition</a>
      <ul>
        <li><a href="#core">Core</a></li>
        <li><a href="#utils">Utils</a></li>
      </ul>
    </li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgements">Acknowledgements</a></li>
  </ol>
</details>

<!-- INTRODUCTION -->
# Introduction

The CX Agent Studio Scripting API (CXAS SCRAPI) is a high-level API that extends the official Google [Python Client for CX Agent Studio](https://docs.cloud.google.com/customer-engagement-ai/conversational-agents/ps). CXAS SCRAPI makes using CX Agent Studio easier, more friendly, and more pythonic for bot builders, developers, and maintainers.

## What Can I Do With CXAS SCRAPI?
With CXAS SCRAPI you can perform many agent building and maintenance actions at scale including, but not limited to:
- Create, Update, Delete, Get, and List for all CXAS resources types (i.e. Apps, Agents, Tools, Guardrails, Deployments, Sessions, etc.)
- Run Evaluations and analyze Conversation History directly through code
- Convert robust Agent responses and configurations into unified, easy-to-read Python dictionaries and dataframes
- Orchestrate and test complex multi-agent setups locally
- Manage App-level Variables and configurations programmatically
- ...and much, much more!

## Built With
* Python 3.10+


<!-- AUTHENTICATION -->
# Authentication  
Authentication can vary depending on how and where you are interacting with SCRAPI.

## Google Colab
If you're using CXAS SCRAPI with a [Google Colab](https://colab.research.google.com/) notebook, you can add the following to the top of your notebook for easy authentication:
```py
project_id = '<YOUR_GCP_PROJECT_ID>'

# this will launch an interactive prompt that allows you to auth with GCP in a browser
!gcloud auth application-default login --no-launch-browser

# this will set your active project to the `project_id` above
!gcloud auth application-default set-quota-project $project_id
```

After running the above, Colab will pick up your credentials from the environment and pass them to CXAS SCRAPI directly. No need to use Service Account keys!
You can then use CXAS SCRAPI simply like this:
```py
from cxas_scrapi import Apps

project_id = '<YOUR_GCP_PROJECT_ID>'
location = 'us'

app_client = Apps(project_id=project_id, location=location) # <-- Creds will be automatically picked up from the environment
apps_map = app_client.get_apps_map()
```
---
## Cloud Functions / Cloud Run
If you're using CXAS SCRAPI with [Cloud Functions](https://cloud.google.com/functions) or [Cloud Run](https://cloud.google.com/run), CXAS SCRAPI can pick up on the default environment creds used by these services without any additional configuration! 

1. Add `cxas-scrapi` to your `requirements.txt` file
2. Ensure the Cloud Function / Cloud Run service account has the appropriate Custom Agent / Conversational Agents IAM Role

Once you are setup with the above, your function code can be used easily like this:
```py
from cxas_scrapi import Agents

app_id = '<YOUR_APP_ID>'
a = Agents(project_id='<YOUR_GCP_PROJECT_ID>', location='global')
agents_map = a.get_agents_map(app_id)
```

---
## Local Python Environment
Similar to Cloud Functions / Cloud Run, CXAS SCRAPI can pick up on your local authentication creds _if you are using the gcloud CLI._

1. Install [gcloud CLI](https://cloud.google.com/sdk/docs/install).
2. Run `gcloud init`.
3. Run `gcloud auth login`
4. Run `gcloud auth application-default login`
5. Run `gcloud auth list` to ensure your principal account is active.

This will authenticate your principal GCP account with the gcloud CLI, and SCRAPI can pick up the creds from here.  

---
## Exceptions and Misc.
If you prefer to explicitly assign Service Account credentials programmatically instead of relying on the environmental `application-default`, you can pass the path to your JSON key using `creds_path`.

```py
from cxas_scrapi import Tools

creds_path = '<PATH_TO_YOUR_SERVICE_ACCOUNT_JSON_FILE>'

t = Tools(project_id='<YOUR_GCP_PROJECT_ID>', location='global', creds_path=creds_path)
tools_map = t.get_tools_map('<YOUR_APP_ID>')
```

<!-- GETTING STARTED -->
# Getting Started
## Environment Setup
Set up Google Cloud Platform credentials and install dependencies.
```sh
gcloud auth login
gcloud auth application-default login
gcloud config set project <project name>
```
```sh
python3 -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
```

## Usage
To run a simple bit of code you can do the following:
- Import a Class from `cxas_scrapi`
- Define your GCP Project and Location

```python
from cxas_scrapi import Apps

# Instantiate your class object and pass in your credentials
app_client = Apps(project_id='<YOUR_GCP_PROJECT_ID>', location='global')

# Retrieve all Apps existing in your project
apps = app_client.list_apps()
for app in apps:
    print(app.display_name, app.name)
```

# Library Composition
Here is a brief overview of the CXAS SCRAPI library's structure and the motivation behind that structure.

## Core  
The `src/cxas_scrapi/core` folder is synonymous with the core Resource types in the CXAS environment (apps, agents, tools, deployments, guardrails, evaluations, etc.)
* This folder contains the high level building blocks of CXAS SCRAPI
* These classes and methods can be used to build higher level methods or custom tools and applications

## Utils
The `src/cxas_scrapi/utils` folder contains various helper functions and logic that perform complex background tasks, such as creating Secret Manager Secrets, pagination, response flattening, and proto conversions.

<!-- CONTRIBUTING -->
# Contributing
We welcome any contributions or feature requests you would like to submit!

1. Fork the Project
2. Create your Feature Branch (git checkout -b feature/AmazingFeature)
3. Commit your Changes (git commit -m 'Add some AmazingFeature')
4. Push to the Branch (git push origin feature/AmazingFeature)
5. Open a Pull Request

<!-- LICENSE -->
# License
Distributed under the Apache 2.0 License. See [LICENSE](LICENSE.txt) for more information.

<!-- CONTACT -->
# Contact
Patrick Marlow - [pmarlow@google.com](mailto:pmarlow@google.com) - [@kmaphoenix](https://github.com/kmaphoenix)  

Project Link: [https://github.com/GoogleCloudPlatform/cxas-scrapi](https://github.com/GoogleCloudPlatform/cxas-scrapi)

<!-- ACKNOWLEDGEMENTS -->
# Acknowledgements
[Google Cloud Customer Engagement AI](https://docs.cloud.google.com/customer-engagement-ai/conversational-agents/ps)
