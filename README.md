# OceanAI_Assignment2_Mail_Agent
An AI-powered email assistant that categorizes messages, extracts actionable tasks, and generates polite reply drafts using Google Gemini. Built with Streamlit and fully local storage, allowing users to edit prompts, refine drafts, and interact with each email through a chat interface.
Made by,
Kumar Abhishek (22BCE1907) Final Year CSC Core student at VIT Chennai

Repository: OceanAI_Assignment2_Mail_Agent
URL: https://github.com/K1I1N1G/OceanAI_Assignment2_Mail_Agent

Demo link: https://drive.google.com/file/d/1I0J69XsTHjy3RPPSjfewj9u2zH6NpWAe/view?usp=sharing

Disclaimer: 
1)The code implementation uses Free tier Gemini 2.5 model. This limits overall API calls per minute and overall API calls per day.
2)The prompts follow structure, hence for categorisation prompt, please add new categories between "[" and "]".
3)In action-item retrieval prompt only modify "Example Response"
4)For mail drafting there are no prompt restrictions, define the kind of mail for which a draft is generated and give a base structure.
NOTE: {These limitations are only due to free tier integration complexities and not due to the codes themselves. Each code has been optimised for best performance.}
________________________________________
🔹 Project Description:
OceanAI Mail Agent is an AI-powered email assistant that uses Google Gemini to:
•	Categorize emails
•	Extract action items
•	Generate editable reply drafts
•	Allow chat-based refinement for each email
All processing is local and user-controlled, with emails stored in JSON.
The system is modular, testable, and extendable, making it suitable for future improvements.
________________________________________
🔹 Setup Instructions
1) Create a Project Folder (Optional)
You may create a folder anywhere on your computer (example: Documents/OceanAI_Project/) to keep things organized.
You can name it anything you like.
________________________________________
2) Download or Clone This Repository
Option A — Using GitHub Desktop (Recommended)
1.	Click the green "Code" button
2.	Select "Open with GitHub Desktop"
3.	Choose your project folder
4.	Click Clone
Option B — Using Command Prompt / PowerShell / Anaconda Terminal
1.	Open a terminal
2.	Navigate to your chosen project folder
3.	Run:
git clone https://github.com/K1I1N1G/OceanAI_Assignment2_Mail_Agent.git
cd OceanAI_Assignment2_Mail_Agent
________________________________________
3) Install Required Packages
Ensure Python 3.10 or newer is installed, then run:
pip install -r requirements.txt
________________________________________
4) Create a Google Gemini API Key
1.	Open: https://aistudio.google.com/app/apikey
2.	Sign in with your Google account
3.	Click Create API Key
4.	Create and add new project and give a name to the key. (Save it)
5.	Copy the generated key
________________________________________
5) Add the API Key to the Project
Open the file:
Agent_Brain/connection_gateway.py
Find the line:
API_KEY = ""
Replace it with your actual API key, like:
API_KEY = "YOUR_REAL_GEMINI_API_KEY"
________________________________________
6) Run the Application
Run the following inside the project folder:
streamlit run app.py
Streamlit will launch automatically in your browser.
________________________________________
🔹 Usage
Once the application opens:
•	The inbox loads immediately
•	AI will process emails in the background automatically
You can:
1.	View, expand, and edit emails using the card buttons
2.	Click the top section of an email to open AI Chat for that specific mail
3.	Chat with the AI to refine or rewrite the reply draft
4.	Edit system prompts in the sidebar to change AI behavior
5.	Use automatic enhancements such as categorization and action item extraction
________________________________________
🔹 Additional Notes
•	Internet connection is required for AI features
•	All emails and AI-generated drafts are stored locally in mail_inbox.json
•	The AI does not automatically send emails — all drafts require manual review and confirmation
________________________________________
End of README


