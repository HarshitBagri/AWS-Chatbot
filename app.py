from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import base64
import io
from PIL import Image
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import logging
import re
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import google.generativeai as genai
from typing import Dict, List, Optional
import requests
import random
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not found in environment variables")

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')

# Enhanced AWS Services Knowledge Base
AWS_SERVICES = {
    'ec2': {
        'name': 'Amazon EC2',
        'description': 'Virtual servers in the cloud',
        'console': 'EC2 Dashboard → Launch Instance → Select AMI → Choose Instance Type → Configure → Launch',
        'cli': 'aws ec2 run-instances --image-id ami-xxxxx --instance-type t2.micro',
        'sdk': 'boto3.client("ec2").run_instances(ImageId="ami-xxx", InstanceType="t2.micro")',
        'troubleshoot': ['Check IAM permissions', 'Verify security groups', 'Check instance state', 'Review VPC settings'],
        'subtopics': ['launch', 'security groups', 'key pairs', 'AMI', 'instance types', 'pricing']
    },
    's3': {
        'name': 'Amazon S3',
        'description': 'Object storage service',
        'console': 'S3 Dashboard → Create Bucket → Enter name → Select region → Create',
        'cli': 'aws s3 mb s3://bucket-name && aws s3 cp file.txt s3://bucket-name/',
        'sdk': 'boto3.client("s3").create_bucket(Bucket="bucket-name")',
        'troubleshoot': ['Check bucket policies', 'Verify IAM permissions', 'Check region settings', 'Review CORS configuration'],
        'subtopics': ['buckets', 'storage classes', 'lifecycle policies', 'versioning', 'encryption', 'static hosting']
    },
    'lambda': {
        'name': 'AWS Lambda',
        'description': 'Serverless compute service',
        'console': 'Lambda Dashboard → Create Function → Select runtime → Write code → Test',
        'cli': 'aws lambda create-function --function-name myFunc --runtime python3.9 --role arn:aws:iam::role',
        'sdk': 'boto3.client("lambda").create_function(FunctionName="myFunc", Runtime="python3.9")',
        'troubleshoot': ['Check CloudWatch logs', 'Verify execution role', 'Check timeout settings', 'Review memory allocation'],
        'subtopics': ['triggers', 'layers', 'environment variables', 'cold starts', 'pricing', 'limits']
    },
    'iam': {
        'name': 'AWS IAM',
        'description': 'Identity and Access Management',
        'console': 'IAM Dashboard → Users/Roles → Create → Attach policies → Review',
        'cli': 'aws iam create-user --user-name myuser && aws iam attach-user-policy',
        'sdk': 'boto3.client("iam").create_user(UserName="myuser")',
        'troubleshoot': ['Check policy syntax', 'Verify permissions', 'Check trust relationships', 'Review MFA settings'],
        'subtopics': ['users', 'roles', 'policies', 'groups', 'MFA', 'access keys', 'federation']
    },
    'vpc': {
        'name': 'Amazon VPC',
        'description': 'Virtual Private Cloud',
        'console': 'VPC Dashboard → Create VPC → Configure subnets → Set up routing',
        'cli': 'aws ec2 create-vpc --cidr-block 10.0.0.0/16',
        'sdk': 'boto3.client("ec2").create_vpc(CidrBlock="10.0.0.0/16")',
        'troubleshoot': ['Check route tables', 'Verify NACL rules', 'Check internet gateway', 'Review peering connections'],
        'subtopics': ['subnets', 'route tables', 'internet gateway', 'NAT gateway', 'VPC peering', 'endpoints']
    },
    'rds': {
        'name': 'Amazon RDS',
        'description': 'Relational Database Service',
        'console': 'RDS Dashboard → Create Database → Choose engine → Configure → Launch',
        'cli': 'aws rds create-db-instance --db-instance-identifier mydb --db-instance-class db.t3.micro',
        'sdk': 'boto3.client("rds").create_db_instance(DBInstanceIdentifier="mydb")',
        'troubleshoot': ['Check security groups', 'Verify subnet groups', 'Check parameter groups', 'Review backup settings'],
        'subtopics': ['engines', 'multi-az', 'read replicas', 'backups', 'encryption', 'performance insights']
    },
    'cloudwatch': {
        'name': 'Amazon CloudWatch',
        'description': 'Monitoring and observability service',
        'console': 'CloudWatch Dashboard → Create Dashboard → Add widgets → Configure metrics',
        'cli': 'aws cloudwatch put-metric-data --namespace "MyApp" --metric-data',
        'sdk': 'boto3.client("cloudwatch").put_metric_data(Namespace="MyApp")',
        'troubleshoot': ['Check metric filters', 'Verify alarm thresholds', 'Review log groups', 'Check retention policies'],
        'subtopics': ['metrics', 'alarms', 'logs', 'dashboards', 'events', 'insights']
    }
}

class ConversationManager:
    """Manage conversation context and follow-up questions"""
    
    def __init__(self):
        self.conversations = {}  # session_id -> conversation data
    
    def get_session_id(self, user_id: str = "default") -> str:
        """Generate or retrieve session ID"""
        return hashlib.md5(f"{user_id}_{datetime.now().date()}".encode()).hexdigest()[:8]
    
    def store_context(self, session_id: str, user_message: str, bot_response: str, 
                     service: str = None, topic: str = None):
        """Store conversation context"""
        if session_id not in self.conversations:
            self.conversations[session_id] = {
                'history': [],
                'current_service': None,
                'current_topic': None,
                'follow_up_count': 0
            }
        
        self.conversations[session_id]['history'].append({
            'user': user_message,
            'bot': bot_response,
            'service': service,
            'topic': topic,
            'timestamp': datetime.now().isoformat()
        })
        
        if service:
            self.conversations[session_id]['current_service'] = service
        if topic:
            self.conversations[session_id]['current_topic'] = topic
    
    def get_context(self, session_id: str) -> Dict:
        """Get conversation context"""
        return self.conversations.get(session_id, {
            'history': [],
            'current_service': None,
            'current_topic': None,
            'follow_up_count': 0
        })
    
    def is_follow_up(self, message: str, context: Dict) -> bool:
        """Check if message is a follow-up question"""
        follow_up_indicators = [
            'aur', 'and', 'also', 'kya', 'how about', 'what about',
            'uske baad', 'phir', 'then', 'next', 'more', 'detail',
            'explain', 'batao', 'samjhao', 'iske alawa'
        ]
        
        return (any(indicator in message.lower() for indicator in follow_up_indicators) 
                and len(context['history']) > 0)

class PracticeQuestionGenerator:
    """Generate dynamic practice questions using Gemini"""
    
    def __init__(self, model):
        self.model = model
        self.generated_questions = {}  # Cache to avoid duplicates
    
    def generate_question(self, service: str, difficulty: str, topic: str = None) -> Dict:
        """Generate a practice question using Gemini AI"""
        try:
            if not self.model:
                return self.get_fallback_question(service, difficulty)
            
            topic_context = f" specifically about {topic}" if topic else ""
            
            prompt = f"""
Generate a practical AWS {service.upper()} practice question{topic_context} for {difficulty} level.

Requirements:
1. Question should be in Hinglish (mix of Hindi and English)
2. Provide 4 multiple choice options
3. Mark the correct answer (0-3 index)
4. Give explanation in Hinglish
5. Make it practical, not theoretical

Difficulty guidelines:
- beginner: Basic concepts, simple commands
- intermediate: Configuration, best practices
- advanced: Complex scenarios, troubleshooting

Return ONLY a JSON object with this structure:
{{
    "question": "Question text in Hinglish",
    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
    "correct": 0,
    "explanation": "Explanation in Hinglish",
    "service": "{service}",
    "difficulty": "{difficulty}",
    "topic": "{topic or 'general'}"
}}
"""
            
            response = self.model.generate_content(prompt)
            question_data = json.loads(response.text.strip())
            
            # Cache the question
            question_key = f"{service}_{difficulty}_{topic or 'general'}"
            if question_key not in self.generated_questions:
                self.generated_questions[question_key] = []
            self.generated_questions[question_key].append(question_data)
            
            return question_data
            
        except Exception as e:
            logger.error(f"Error generating question: {str(e)}")
            return self.get_fallback_question(service, difficulty)
    
    def get_fallback_question(self, service: str, difficulty: str) -> Dict:
        """Fallback questions when Gemini is not available"""
        fallback_questions = {
            's3_beginner': {
                'question': 'S3 bucket create karne ke liye minimum kya chahiye?',
                'options': ['Bucket name aur region', 'Only bucket name', 'Name, region aur policy', 'AWS account only'],
                'correct': 0,
                'explanation': 'Bucket name unique hona chahiye globally aur region select karna zaroori hai.',
                'service': 's3',
                'difficulty': 'beginner',
                'topic': 'basic'
            },
            'ec2_intermediate': {
                'question': 'Production environment ke liye EC2 instance choose karte time kya consider karna chahiye?',
                'options': ['Only price', 'CPU aur memory requirements', 'All resources aur redundancy', 'Storage type only'],
                'correct': 2,
                'explanation': 'Production mein CPU, memory, storage, network aur high availability sab consider karna padta hai yaar.',
                'service': 'ec2',
                'difficulty': 'intermediate', 
                'topic': 'production'
            }
        }
        
        key = f"{service}_{difficulty}"
        return fallback_questions.get(key, {
            'question': f'{service.upper()} ke baare mein ek question generate nahi kar paya yaar!',
            'options': ['Try again', 'Different service', 'Check connection', 'Contact support'],
            'correct': 0,
            'explanation': 'Technical issue hai, phir se try karo.',
            'service': service,
            'difficulty': difficulty,
            'topic': 'error'
        })

class OptimizedAWSChatbot:
    def __init__(self):
        self.conversation_manager = ConversationManager()
        self.question_generator = PracticeQuestionGenerator(model if GEMINI_API_KEY else None)
        self.gemini_available = GEMINI_API_KEY is not None
        
    def create_enhanced_prompt(self, message: str, context: Dict, detected_service: str = None) -> str:
        """Create enhanced prompt with formatting instructions"""
        
        context_info = ""
        if context['current_service']:
            context_info = f"Previous context: User was asking about {context['current_service']}"
            if context['current_topic']:
                context_info += f" specifically {context['current_topic']}"
        
        if context['history']:
            recent_history = context['history'][-2:]  # Last 2 exchanges
            context_info += f"\nRecent conversation: {json.dumps(recent_history)}"

        return f"""
You are an AWS expert who speaks in natural Hinglish and provides well-structured responses.

FORMATTING RULES (VERY IMPORTANT):
1. Use bullet points (•) for lists of features, steps, or options
2. Use numbered points (1. 2. 3.) for sequential steps or procedures  
3. Use **bold** for important terms and headings
4. Use `code blocks` for commands and code
5. Write in paragraphs when explaining concepts
6. Always end with a follow-up question to continue the conversation

RESPONSE STRUCTURE:
- Start with a brief explanation paragraph
- Use bullet points or numbered lists as appropriate
- Include practical examples
- End with "Aur kuch puchna hai iske baare mein?" or similar

TONE: Friendly Hinglish - use "yaar", "bhai", "dekho", naturally

{context_info}

User's question: {message}
{f"Detected service: {detected_service}" if detected_service else ""}

Provide a helpful, well-formatted response in Hinglish.
        """

    def detect_service(self, message: str) -> Optional[str]:
        """Enhanced service detection"""
        service_keywords = {
            'ec2': ['ec2', 'instance', 'server', 'virtual machine', 'ami', 'compute'],
            's3': ['s3', 'bucket', 'storage', 'object', 'file storage'],
            'lambda': ['lambda', 'serverless', 'function', 'faas'],
            'iam': ['iam', 'user', 'role', 'permission', 'policy', 'access'],
            'vpc': ['vpc', 'network', 'subnet', 'security group', 'routing'],
            'rds': ['rds', 'database', 'mysql', 'postgres', 'sql'],
            'cloudwatch': ['cloudwatch', 'monitoring', 'logs', 'metrics', 'alarm']
        }
        
        msg_lower = message.lower()
        scores = {}
        
        for service, keywords in service_keywords.items():
            score = sum(2 if keyword in msg_lower else 0 for keyword in keywords)
            if score > 0:
                scores[service] = score
        
        return max(scores, key=scores.get) if scores else None

    def detect_topic(self, message: str, service: str) -> Optional[str]:
        """Detect specific topic within a service"""
        if not service or service not in AWS_SERVICES:
            return None
            
        subtopics = AWS_SERVICES[service].get('subtopics', [])
        msg_lower = message.lower()
        
        for topic in subtopics:
            if topic.lower() in msg_lower:
                return topic
        return None

    def format_service_info(self, service: str, access_method: str = None, topic: str = None) -> str:
        """Format service information with proper structure"""
        if service not in AWS_SERVICES:
            return f"Sorry yaar, {service} ke baare mein detailed info nahi hai abhi."
        
        service_info = AWS_SERVICES[service]
        
        response = f"## **{service_info['name']}**\n\n"
        response += f"{service_info['description']}\n\n"
        
        if topic:
            response += f"**{topic.title()}** ke baare mein specific info:\n\n"
        
        if access_method:
            if access_method == 'console':
                response += f"**Console Steps:**\n{service_info['console']}\n\n"
            elif access_method == 'cli':
                response += f"**CLI Command:**\n```bash\n{service_info['cli']}\n```\n\n"
            elif access_method == 'sdk':
                response += f"**SDK Code:**\n```python\n{service_info['sdk']}\n```\n\n"
        else:
            response += "**Access kaise kare:**\n"
            response += f"• **Console**: {service_info['console']}\n"
            response += f"• **CLI**: `{service_info['cli']}`\n"
            response += f"• **SDK**: `{service_info['sdk']}`\n\n"
        
        response += "**Common Issues aur Solutions:**\n"
        for i, issue in enumerate(service_info['troubleshoot'], 1):
            response += f"{i}. {issue}\n"
        
        if service_info.get('subtopics'):
            response += f"\n**Related Topics:** {', '.join(service_info['subtopics'])}\n"
        
        response += f"\n{service.upper()} ke baare mein aur kya jaanna hai?"
        
        return response

    def process_message(self, message: str, image_data: Optional[str] = None, 
                       session_id: str = None) -> Dict:
        """Enhanced message processing with follow-up handling"""
        
        if not session_id:
            session_id = self.conversation_manager.get_session_id()
        
        context = self.conversation_manager.get_context(session_id)
        
        response = {
            'message': '',
            'service_info': None,
            'code_examples': None,
            'troubleshooting': None,
            'practice_question': None,
            'session_id': session_id,
            'follow_up_suggestions': []
        }
        
        try:
            # Handle greetings
            if any(greeting in message.lower() for greeting in ['hello', 'hi', 'hey', 'namaste', 'aur bhai']):
                response['message'] = """# **Namaste yaar! 🙏 AWS Expert Assistant**

AWS sikhne aur troubleshoot karne ke liye ready hun!

## **Main kya kar sakta hun:**

• **Service Explanations** - EC2, S3, Lambda, IAM, VPC, RDS, CloudWatch
• **Step-by-Step Guides** - Console, CLI, aur SDK sab methods
• **Troubleshooting Help** - Problems solve karne mein madad  
• **Practice Questions** - Dynamic AI-generated quiz
• **Screenshot Analysis** - AWS console ki images dekh kar help
• **Follow-up Support** - Detailed discussions

## **Popular Services:**
1. **EC2** - Virtual servers aur compute
2. **S3** - Object storage aur static hosting  
3. **Lambda** - Serverless functions
4. **IAM** - Users aur permissions

Kya sikhna chahte ho today? 🚀"""
                
                self.conversation_manager.store_context(session_id, message, response['message'])
                return response

            # Handle practice questions with dynamic generation
            if any(word in message.lower() for word in ['practice', 'quiz', 'question', 'test']):
                difficulty = 'advanced' if 'advanced' in message.lower() else 'intermediate' if 'intermediate' in message.lower() else 'beginner'
                
                # Try to detect service for targeted questions
                detected_service = self.detect_service(message) or context.get('current_service', 'general')
                topic = self.detect_topic(message, detected_service) if detected_service != 'general' else None
                
                if detected_service != 'general':
                    response['practice_question'] = self.question_generator.generate_question(
                        detected_service, difficulty, topic
                    )
                    response['message'] = f"**{detected_service.upper()} Practice Question** ({difficulty} level) 🤔"
                else:
                    # Generate question for random service
                    random_service = random.choice(list(AWS_SERVICES.keys()))
                    response['practice_question'] = self.question_generator.generate_question(
                        random_service, difficulty
                    )
                    response['message'] = f"**Random AWS Practice Question** ({difficulty} level) 🤔"
                
                self.conversation_manager.store_context(session_id, message, response['message'])
                return response

            # Detect service, topic and access method
            detected_service = self.detect_service(message)
            detected_topic = self.detect_topic(message, detected_service) if detected_service else None
            access_method = self.detect_access_method(message)
            
            # Handle follow-up questions
            is_follow_up = self.conversation_manager.is_follow_up(message, context)
            
            if is_follow_up and context['current_service']:
                detected_service = detected_service or context['current_service']
                message = f"Follow-up about {context['current_service']}: {message}"

            # Handle image analysis
            if image_data:
                response['message'] = self.analyze_screenshot(image_data, message, context)
                self.conversation_manager.store_context(session_id, message, response['message'])
                return response

            # Generate response using Gemini if available
            if self.gemini_available:
                enhanced_prompt = self.create_enhanced_prompt(message, context, detected_service)
                gemini_response = model.generate_content(enhanced_prompt)
                response['message'] = gemini_response.text
                
                # Add service-specific structured info if detected
                if detected_service:
                    response['service_info'] = AWS_SERVICES.get(detected_service)
                    
            else:
                # Fallback response with structured formatting
                if detected_service:
                    response['message'] = self.format_service_info(detected_service, access_method, detected_topic)
                    response['service_info'] = AWS_SERVICES.get(detected_service)
                else:
                    response['message'] = """# **AWS Services Available**

Main tumhe ye sab services mein help kar sakta hun:

## **Compute Services:**
• **EC2** - Virtual servers aur instances
• **Lambda** - Serverless functions

## **Storage Services:**  
• **S3** - Object storage aur static hosting

## **Database Services:**
• **RDS** - Managed relational databases

## **Networking:**
• **VPC** - Virtual private cloud

## **Security:**
• **IAM** - Identity and access management

## **Monitoring:**
• **CloudWatch** - Logs aur metrics

**Kya specific service ke baare mein jaanna hai?** 
Format: "S3 console mein kaise use kare" ya "EC2 troubleshoot karo" 🤔"""

            # Generate follow-up suggestions
            if detected_service:
                service_info = AWS_SERVICES.get(detected_service, {})
                subtopics = service_info.get('subtopics', [])
                response['follow_up_suggestions'] = [
                    f"{detected_service.upper()} {topic} ke baare mein batao" 
                    for topic in subtopics[:3]
                ]

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            response['message'] = """**Oops! Technical Issue 😅**

Kuch gadbad ho gayi yaar! Possible solutions:

1. **Phir se try karo** - Message resend kar do
2. **Simple language** - Basic English ya Hindi mein poocho  
3. **Specific question** - Exact service name mention karo

**Example:** "S3 bucket kaise banate hain console mein?"

Main phir ready hun! 🚀"""
        
        # Store conversation context
        self.conversation_manager.store_context(
            session_id, message, response['message'], 
            detected_service, detected_topic
        )
        
        return response

    def detect_access_method(self, message: str) -> Optional[str]:
        """Detect AWS access method from message"""
        msg_lower = message.lower()
        if any(word in msg_lower for word in ['console', 'gui', 'dashboard', 'web', 'ui']):
            return 'console'
        elif any(word in msg_lower for word in ['cli', 'command', 'terminal', 'cmd']):
            return 'cli'
        elif any(word in msg_lower for word in ['sdk', 'python', 'boto3', 'code', 'javascript', 'api']):
            return 'sdk'
        return None

    def analyze_screenshot(self, image_data: str, message: str, context: Dict) -> str:
        """Analyze AWS console screenshot with enhanced formatting"""
        try:
            if not self.gemini_available:
                return """**Screenshot Analysis Not Available** 📷

Gemini API key nahi mila yaar! 

**Alternative Solutions:**
1. **Describe karo** - Text mein batao kya dikh raha hai
2. **Error message** - Jo error aa rahi hai wo copy paste kar do  
3. **Service name** - Konsi AWS service use kar rahe ho

**API Key setup ke liye:** `export GEMINI_API_KEY='your-key'`"""
                
            # Decode image
            image_bytes = base64.b64decode(image_data.split(',')[1])
            image = Image.open(io.BytesIO(image_bytes))
            
            context_info = ""
            if context.get('current_service'):
                context_info = f"User is working with {context['current_service']}"
            
            prompt = f"""
Analyze this AWS console screenshot and provide structured response in Hinglish.

Context: {context_info}
User question: {message}

Provide response in this format:
**Service Detected:** [service name]

**Current Status:** [what's happening]  

**Issues Found:**
• [issue 1]
• [issue 2]

**Solutions:**
1. [step 1]
2. [step 2] 
3. [step 3]

**Next Steps:**
What should they do next?

Keep it practical and in Hinglish tone.
            """
            
            response = model.generate_content([prompt, image])
            return response.text
            
        except Exception as e:
            logger.error(f"Error analyzing image: {str(e)}")
            return """**Screenshot Analysis Failed** 😅

Image process nahi kar paya yaar!

**Alternatives:**
• **Describe karo** - Text mein detail batao
• **Error code** - Exact error message share karo
• **Console section** - Konsa AWS service page khula hai

Phir main help kar sakta hun! 🔧"""

# Initialize chatbot
chatbot = OptimizedAWSChatbot()

@app.route('/api/chat', methods=['POST'])
def chat():
    """Enhanced chat endpoint with session management"""
    try:
        data = request.json
        message = data.get('message', '')
        image_data = data.get('image', None)
        session_id = data.get('session_id', None)
        
        if not message and not image_data:
            return jsonify({'error': 'Message ya image toh bhejo yaar!'}), 400
        
        response = chatbot.process_message(message, image_data, session_id)
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return jsonify({'error': 'Server mein problem hai yaar! Phir se try karo.'}), 500

@app.route('/api/services', methods=['GET'])
def get_services():
    """Get list of supported AWS services with details"""
    services_list = []
    for key, service in AWS_SERVICES.items():
        services_list.append({
            'id': key,
            'name': service['name'],
            'description': service['description'],
            'subtopics': service.get('subtopics', [])
        })
    return jsonify(services_list)

@app.route('/api/practice', methods=['POST'])
def get_practice_question():
    """Generate dynamic practice question"""
    try:
        data = request.json or {}
        difficulty = data.get('difficulty', 'beginner')
        service = data.get('service', random.choice(list(AWS_SERVICES.keys())))
        topic = data.get('topic', None)
        
        if difficulty not in ['beginner', 'intermediate', 'advanced']:
            return jsonify({'error': 'Invalid difficulty level yaar!'}), 400
        
        if service not in AWS_SERVICES:
            return jsonify({'error': f'{service} supported nahi hai yaar!'}), 400
        
        question = chatbot.question_generator.generate_question(service, difficulty, topic)
        return jsonify(question)
        
    except Exception as e:
        logger.error(f"Practice question error: {str(e)}")
        return jsonify({'error': 'Question generate nahi kar paya!'}), 500

@app.route('/api/conversation/<session_id>', methods=['GET'])
def get_conversation_history(session_id):
    """Get conversation history for a session"""
    try:
        context = chatbot.conversation_manager.get_context(session_id)
        return jsonify({
            'session_id': session_id,
            'history': context['history'],
            'current_service': context.get('current_service'),
            'current_topic': context.get('current_topic')
        })
    except Exception as e:
        logger.error(f"Conversation history error: {str(e)}")
        return jsonify({'error': 'History nahi mil paya!'}), 500

@app.route('/api/conversation/<session_id>', methods=['DELETE'])
def clear_conversation(session_id):
    """Clear conversation history"""
    try:
        if session_id in chatbot.conversation_manager.conversations:
            del chatbot.conversation_manager.conversations[session_id]
        return jsonify({'message': 'Conversation cleared successfully!'})
    except Exception as e:
        logger.error(f"Clear conversation error: {str(e)}")
        return jsonify({'error': 'Clear nahi kar paya!'}), 500

# @app.route('/api/health', methods=['GET'])
# def health_check():
#     """Enhanced health check"""
#     return jsonify({
#         'status': 'All systems good yaar! 👍',
#         'timestamp': datetime.now().isoformat(),
#         'features': {
#             'gemini_ai': chatbot.gemini_available,
#             'dynamic_questions': True,
#             'follow_up_support': True,
#             'image_analysis

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'All good yaar! 👍',
        'timestamp': datetime.now().isoformat(),
        'gemini_available': chatbot.gemini_available
    })

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration status"""
    return jsonify({
        'gemini_configured': GEMINI_API_KEY is not None,
        'services_count': len(AWS_SERVICES),
        'question_categories': list(get_practice_question.keys())
    })

if __name__ == '__main__':
    if not GEMINI_API_KEY:
        print("⚠️  WARNING: GEMINI_API_KEY nahi mila yaar!")
        print("   Chatbot basic functionality ke saath chalega.")
        print("   Full features ke liye API key set karo:")
        print("   export GEMINI_API_KEY='your-api-key-here'")
    else:
        print("✅ Gemini API key configured hai! Chalo start karte hain! 🚀")
    
    app.run(debug=True, host='0.0.0.0', port=5000)