# my_tiny_app/routes/admin.py
from flask import Blueprint,render_template,jsonify,session,request
import json
from flask import current_app as app
from models import Conversation, Message, db
import google.generativeai as genai
import logging
from db_tools import get_applicant_info, get_job_details, get_jobs_by_type, get_applications_by_status


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


chat_bp = Blueprint('chat_bp', __name__)


model = genai.GenerativeModel(
    'gemini-1.5-flash', # Using a stable, generally available model
    system_instruction=(
       "You are 'Spryple Bot', a friendly and helpful AI assistant for **Spryple Solutions**. "
        "Your main goal is to provide information about Spryple, its job openings, and applicant details. "
        "Here are some key facts about Spryple that you should use to answer questions:\n"
        "- **Founders:** Spryple was founded by Venkateswarlu Boora and Sree Lahari Raavi.\n"
        "- **CEO:** Venkateswarlu Boora also holds the position of CEO at Spryple.\n"
        "- **Website:** You can find more information on their official website at https://spryple.com/.\n"
        "- **What they do:** Spryple is a technology company specializing in Human Resources (HR) solutions. They aim to simplify and improve various HR processes for businesses.\n"
        "- **Key offerings:** Their platform likely includes tools for recruiting, employee onboarding, performance management, and other essential HR tasks, striving for a comprehensive and efficient HR tech solution.\n\n"
        "**Crucially, you HAVE ACCESS to a set of powerful tools to query the database about jobs and applications. YOU MUST USE THESE TOOLS WHENEVER the user's query can be answered by one of them.**\n"
        "**When using a tool, you are responsible for extracting ALL necessary parameters from the user's query.**\n"
        "**Here are the tools you can use and when to use them:**\n"
        "- **Applicant Details (get_applicant_info):** Use this to find information about a specific applicant, including their email, status, or other general details. Trigger this if the user asks for an applicant's name (full or partial) or email. \n"
        "  * **Input:** Always pass the user's provided name or email directly as `applicant_identifier` or `applicant_email`. For example, if the user says 'Charan', pass `applicant_identifier='Charan'`. \n"
        "  * **Output Handling:**\n"
        "    * If the tool returns an **empty list `[]`**: Inform the user clearly that no applicant was found matching the given criteria (e.g., 'I couldn't find any applicant named [Name].').\n"
        "    * If the tool returns **exactly one result**: Provide the requested information directly and concisely (e.g., 'The email for [Applicant Name] is [Email Address].').\n"
        "    * If the tool returns **multiple results**: State that multiple applicants were found. List their full names (and perhaps the job title they applied for if available in the tool's output) and politely ask the user to provide the full name or more specific details to identify the correct person. For example: 'I found multiple applicants matching [Partial Name]: [Name 1], [Name 2], etc. Could you please specify the full name of the person you're looking for?'\n"

        "- **Job Details (get_job_details):** Use this to get specific descriptions, locations, or requirements for a job opening. Trigger this if the user asks for details about a job title.\n"
        "  *Example Usage:* `get_job_details(job_title='Software Engineer')`\n"
        "- **Jobs by Type (get_jobs_by_type):** Use this to list jobs based on their employment type (e.g., 'full-time', 'contract'). Trigger this if the user asks for jobs of a certain type.\n"
        "  *Example Usage:* `get_jobs_by_type(job_type='Full-time')`\n"
        "- **Applications by Status (get_applications_by_status):** Use this to list applications based on their current status (e.g., 'Pending', 'Approved', 'Rejected'). Trigger this if the user asks for applications with a specific status.\n"
        "  *Example Usage:* `get_applications_by_status(status='Approved')`\n"
        
        # If you've added get_applicants_by_job_title:
        # "- **Applicants for a Specific Job (get_applicants_by_job_title):** Use this to find applicants who applied for a particular job title. Trigger this if the user asks 'who applied for [job title]?' or 'list candidates for [job title]'.\n"
        # "  *Example Usage:* `get_applicants_by_job_title(job_title='HR Manager')`\n"
        "\n"
        "**General Output Handling (Applies after specific tool handling rules):**\n"
        "After using a tool, summarize the information clearly and concisely in natural language to the user. "
        "If a question is outside the scope of Spryple Solutions, its jobs, or applications, or you don't have the information based on the facts provided, "
        "politely state that you only have information about Spryple and cannot answer questions on other topics or details you haven't been given."
    
        # If you've added get_applicants_by_job_title:
        # "- **Applicants for a Specific Job (get_applicants_by_job_title):** Use this to find applicants who applied for a particular job title. Trigger this if the user asks 'who applied for [job title]?' or 'list candidates for [job title]'.\n"
        # "  *Example Usage:* `get_applicants_by_job_title(job_title='HR Manager')`\n"
        "\n"
        "**AFTER you use a tool:**\n"
        "1.  **If the tool returns an empty list `[]`:** Inform the user clearly that no matching information was found. For example: 'I couldn't find any applicant named [Name].' or 'No jobs of that type were found.' **Do NOT mention privacy if the tool found nothing.**\n"
        "2.  **If the tool returns data:** Summarize the information clearly and concisely in natural language to the user. Provide the specific details the user asked for (e.g., an email address, job description). Your goal is to be helpful and direct with the information retrieved by the tools.\n"
        "\n"
        "If a question is outside the scope of Spryple Solutions, its jobs, or applications, or you don't have the information based on the facts provided, "
        "politely state that you only have information about Spryple and cannot answer questions on other topics or details you haven't been given."
),
    tools=[get_applicant_info, get_job_details, get_jobs_by_type, get_applications_by_status] # Register your tools here
 )


# --- Helper function for starting/getting chat session history ---
def get_gemini_chat_history(conversation_id):
    """Retrieves conversation history from the database for Gemini."""
    messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
    history = []
    for msg in messages:
        role = 'user' if msg.sender == 'user' else 'model' # Gemini uses 'model' for bot responses
        history.append({'role': role, 'parts': [msg.content]})
    return history

# Define a dictionary to map tool names (strings) to their actual functions
# This is crucial for executing the tool calls dynamically
available_tools = {
    'get_applicant_info': get_applicant_info,
    'get_job_details': get_job_details,
    'get_jobs_by_type': get_jobs_by_type,
    'get_applications_by_status': get_applications_by_status
}



@chat_bp.route('/start_new', methods=['POST'])
def start_new_conversation():
    """Starts a new conversation and returns its ID."""
    try:
        new_conversation = Conversation(metadata=json.dumps({"topic": "general_inquiry"})) # Add more metadata as needed
        db.session.add(new_conversation)
        db.session.commit()
        session['conversation_id'] = new_conversation.id # Store conversation ID in session
        return jsonify({"conversation_id": new_conversation.id, "message": "New conversation started."}), 201
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error starting new conversation: {e}")
        return jsonify({"message": "Failed to start new conversation."}), 500

@chat_bp.route('/message', methods=['POST'])
def send_chat_message():
    data = request.get_json()
    user_message_content = data.get('message')
    conversation_id = data.get('conversation_id') # Get ID from frontend if provided

    if not user_message_content:
        return jsonify({"message": "No message provided."}), 400

    if not conversation_id:
        # If no conversation ID, start a new one automatically
        new_conversation = Conversation(conversation_info=json.dumps({"topic": "auto_start"}))
        db.session.add(new_conversation)
        db.session.commit()
        conversation_id = new_conversation.id
        app.logger.info(f"Auto-started new conversation: {conversation_id}")
    else:
        # Ensure the conversation exists
        existing_conv = Conversation.query.get(conversation_id)
        if not existing_conv:
            return jsonify({"message": "Conversation not found."}), 404

    try:
        # 1. Save user message to DB
        user_message_db = Message(
            conversation_id=conversation_id,
            sender='user',
            content=user_message_content
        )
        db.session.add(user_message_db)
        db.session.commit()

        # 2. Get historical messages for Gemini
        gemini_history = get_gemini_chat_history(conversation_id)
        # The last message added to history *is* the current user message.
        # Gemini's `start_chat` history parameter expects the history *before* the current turn.
        # The current message is then sent via `send_message`.
        # So, we should *not* remove the last user message from `gemini_history` if it's already there
        # because the `send_message` call is designed for the current turn.
        # If get_gemini_chat_history includes the current user message, then it's wrong.
        # Let's assume get_gemini_chat_history fetches everything *up to and including* the last user message saved.
        # So we pass the full history to start_chat, then send the message again.
        # This is a common pattern for "continuation" of a chat session.

        # If you want to use start_chat with *only previous* messages and then send the new one:
        # gemini_history_for_start = get_gemini_chat_history(conversation_id)
        # if gemini_history_for_start and gemini_history_for_start[-1]['role'] == 'user' and gemini_history_for_start[-1]['parts'][0] == user_message_content:
        #     gemini_history_for_start = gemini_history_for_start[:-1] # Remove current user message from history for start_chat

        chat_session = model.start_chat(history=gemini_history)
        gemini_response = chat_session.send_message(user_message_content)
        print("message sent to Gemini")
        bot_response_content = ""
        tool_outputs = []

        # Check for tool calls
        if gemini_response.candidates and gemini_response.candidates[0].content.parts:
            for part in gemini_response.candidates[0].content.parts:
                if part.function_call:
                    tool_call = part.function_call
                    tool_name = tool_call.name
                    tool_args = {k: v for k, v in tool_call.args.items()} # Convert to dict
                    print("tools")
                    print(tool_name)
                    print(tool_args)

                    app.logger.info(f"Gemini requested tool: {tool_name} with args: {tool_args}")

                    if tool_name in available_tools:
                        tool_func = available_tools[tool_name]
                        # Execute the tool and capture its output
                        try:
                            # IMPORTANT: You might need to run tool_func within an app context
                            # if it relies on db.session directly and this route is not implicitly in context.
                            # For Flask, typically, routes are in app context.
                            with app.app_context(): # Ensure DB operations are in app context
                                tool_result = tool_func(**tool_args)
                            tool_outputs.append({
                                "tool_code": tool_name,
                                "tool_input": tool_args,
                                "tool_output": tool_result
                            })
                            app.logger.info(f"Tool {tool_name} executed. Result: {tool_result}")

                            # Send tool output back to Gemini
                            gemini_response_after_tool = chat_session.send_message(
                                genai.protos.Part(function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response={ "result": json.dumps(tool_result) } # Gemini expects a dict for response
                                ))
                            )
                            # The final bot response will be in this second gemini_response
                            bot_response_content = gemini_response_after_tool.text
                            if not bot_response_content:
                                bot_response_content = f"I used the {tool_name} tool. Here's what I found: {json.dumps(tool_result, indent=2)}"


                        except Exception as tool_e:
                            app.logger.error(f"Error executing tool {tool_name}: {tool_e}")
                            tool_outputs.append({
                                "tool_code": tool_name,
                                "tool_input": tool_args,
                                "tool_output": f"Error executing tool: {tool_e}"
                            })
                            bot_response_content = f"I tried to use a tool to get that information, but encountered an error: {tool_e}. Please try again."
                            # Send error back to Gemini so it knows the tool failed
                            chat_session.send_message(
                                genai.protos.Part(function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response={ "error": str(tool_e) }
                                ))
                            )
                            # If no further text from bot after error, use a generic message
                            if not bot_response_content:
                                bot_response_content = "I'm sorry, I couldn't retrieve the information due to an internal error."

                else:
                    # If it's not a tool call, it's a regular text response
                    bot_response_content += part.text
        else:
            # No candidates or parts, so it's likely a direct text response or an empty one
            print("no tool calls found actually")
            bot_response_content = gemini_response.text


        # If bot_response_content is still empty (e.g., if tool call didn't yield text immediately)
        if not bot_response_content:
            bot_response_content = "I'm sorry, I couldn't generate a response. Can you please rephrase?"


        # 4. Save bot message to DB
        bot_message_db = Message(
            conversation_id=conversation_id,
            sender='bot',
            content=bot_response_content
        )
        db.session.add(bot_message_db)
        db.session.commit()

        return jsonify({
            "user_message": user_message_db.to_dict(),
            "bot_message": bot_message_db.to_dict(),
            "tool_outputs": tool_outputs # Optionally return tool outputs for debugging
        }), 200

    except Exception as e:
        db.session.rollback() # Rollback in case of error
        app.logger.error(f"Error processing chat message: {e}")
        # Provide a default bot response in case of any API error
        error_bot_response = "I'm sorry, I encountered an internal issue. Please try again or check my API key."
        bot_message_db = Message(
            conversation_id=conversation_id,
            sender='bot',
            content=error_bot_response
        )
        db.session.add(bot_message_db)
        db.session.commit()
        return jsonify({
            "message": "Failed to process message.",
            "user_message": user_message_db.to_dict(), # Still return user message if saved
            "bot_message": bot_message_db.to_dict() # Return error message from bot
        }), 500
    

@chat_bp.route('/history/<int:conversation_id>', methods=['GET'])
def get_conversation_history(conversation_id):
    """Fetches all messages for a given conversation ID."""
    conversation = Conversation.query.get(conversation_id)
    if not conversation:
        return jsonify({"message": "Conversation not found."}), 404

    # messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
    # return jsonify([msg.to_dict() for msg in messages]), 200
    # Using the to_dict method on the Conversation model for a complete response
    return jsonify(conversation.to_dict()), 200


@chat_bp.route('/conversations', methods=['GET'])
def get_all_conversations():
    """Fetches a list of all past conversations."""
    conversations = Conversation.query.order_by(Conversation.started_at.desc()).all()
    # Return a summary, not all messages to avoid large payload
    summary_conversations = []
    for conv in conversations:
        first_message = Message.query.filter_by(conversation_id=conv.id).order_by(Message.timestamp).first()
        summary_conversations.append({
            'id': conv.id,
            'started_at': conv.started_at.isoformat(),
            'first_message_preview': first_message.content if first_message else "No messages yet",
            'message_count': len(conv.messages)
        })
    return jsonify(summary_conversations), 200