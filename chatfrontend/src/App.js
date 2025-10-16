import React, { useState, useRef, useEffect } from 'react';
import { Send, Upload, Image, Code, Terminal, Globe, HelpCircle, CheckCircle, XCircle } from 'lucide-react';
import './App.css'; // Import the CSS file

const App = () => {
  const [messages, setMessages] = useState([
    {
      id: 1,
      type: 'bot',
      content: "Hello! I'm your AWS assistant. I can help you with AWS services through CLI, Management Console, and SDK. I can also provide troubleshooting help and practice questions. What would you like to learn about?",
      timestamp: new Date()
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const [showPracticeQuestion, setShowPracticeQuestion] = useState(null);
  const [selectedAnswer, setSelectedAnswer] = useState(null);
  const [showAnswer, setShowAnswer] = useState(false);
  const [practiceScore, setPracticeScore] = useState({ correct: 0, total: 0 });
  
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  const handleSendMessage = async () => {
    if (!inputMessage.trim() && !selectedImage) return;
    
    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputMessage,
      image: selectedImage,
      timestamp: new Date()
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setSelectedImage(null);
    setIsLoading(true);
    
    try {
      const response = await fetch('http://localhost:5000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: inputMessage,
          image: selectedImage
        }),
      });
      
      const data = await response.json();
      
      const botMessage = {
        id: Date.now() + 1,
        type: 'bot',
        content: data.message,
        serviceInfo: data.service_info,
        codeExamples: data.code_examples,
        troubleshooting: data.troubleshooting,
        practiceQuestion: data.practice_question,
        timestamp: new Date()
      };
      
      setMessages(prev => [...prev, botMessage]);
      
      if (data.practice_question) {
        setShowPracticeQuestion(data.practice_question);
        setSelectedAnswer(null);
        setShowAnswer(false);
      }
      
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = {
        id: Date.now() + 1,
        type: 'bot',
        content: 'Sorry, I encountered an error. Please make sure the backend server is running on port 5000.',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    }
    
    setIsLoading(false);
  };
  
  const handleImageUpload = (event) => {
    const file = event.target.files[0];
    if (file && file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = (e) => {
        setSelectedImage(e.target.result);
      };
      reader.readAsDataURL(file);
    }
  };
  
  const handlePracticeAnswer = (answerIndex) => {
    setSelectedAnswer(answerIndex);
    setShowAnswer(true);
    
    const isCorrect = answerIndex === showPracticeQuestion.correct;
    setPracticeScore(prev => ({
      correct: prev.correct + (isCorrect ? 1 : 0),
      total: prev.total + 1
    }));
  };
  
  const quickActions = [
    { icon: Terminal, text: 'CLI Commands', action: () => setInputMessage('Show me CLI commands for EC2') },
    { icon: Globe, text: 'Console Steps', action: () => setInputMessage('How to use S3 in Management Console') },
    { icon: Code, text: 'SDK Examples', action: () => setInputMessage('Show me Python SDK examples for Lambda') },
    { icon: HelpCircle, text: 'Practice Quiz', action: () => setInputMessage('Give me a practice question') }
  ];
  
  const formatMessage = (message) => {
    if (typeof message === 'string') {
      return message;
    }
    return JSON.stringify(message, null, 2);
  };
  
  return (
    <div className="aws-chatbot-container">
      {/* Header */}
      <div className="header">
        <div className="header-content">
          <div className="header-left">
            <div className="aws-logo">
              <span>AWS</span>
            </div>
            <div className="header-info">
              <h1>AWS Assistant</h1>
              <p>CLI • Console • SDK • Troubleshooting</p>
            </div>
          </div>
          <div className="score-display">
            <div className="score-label">Practice Score</div>
            <div className="score-value">
              {practiceScore.correct}/{practiceScore.total}
            </div>
          </div>
        </div>
      </div>
      
      {/* Messages */}
      <div className="message-container">
        <div className="messages-wrapper">
          {messages.map((message) => (
            <div key={message.id} className={`message-row ${message.type}`}>
              <div className={`message-bubble ${message.type}-message`}>
                <div className="message-content">
                  {formatMessage(message.content)}
                </div>
                
                {message.image && (
                  <div className="message-image">
                    <img
                      src={message.image}
                      alt="Uploaded screenshot"
                      className="uploaded-image"
                    />
                  </div>
                )}
                
                {message.serviceInfo && (
                  <div className="service-info">
                    <h4 className="service-title">
                      {message.serviceInfo.name}
                    </h4>
                    <p className="service-description">
                      {message.serviceInfo.description}
                    </p>
                  </div>
                )}
                
                {message.codeExamples && (
                  <div className="code-examples">
                    <h4 className="code-title">
                      <Code className="icon" />
                      Code Examples
                    </h4>
                    <div className="code-blocks">
                      {Array.isArray(message.codeExamples) ? (
                        message.codeExamples.map((example, index) => (
                          <div key={index} className="code-block">
                            {example}
                          </div>
                        ))
                      ) : (
                        Object.entries(message.codeExamples).map(([lang, code]) => (
                          <div key={lang} className="code-section">
                            <div className="code-lang">{lang}</div>
                            <div className="code-block">
                              {code}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
                
                {message.troubleshooting && (
                  <div className="troubleshooting">
                    <h4 className="troubleshooting-title">
                      Troubleshooting Steps
                    </h4>
                    <ul className="troubleshooting-list">
                      {message.troubleshooting.map((step, index) => (
                        <li key={index} className="troubleshooting-item">
                          <span className="bullet">•</span>
                          {step}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                
                <div className="timestamp">
                  {message.timestamp.toLocaleTimeString()}
                </div>
              </div>
            </div>
          ))}
          
          {isLoading && (
            <div className="message-row bot">
              <div className="message-bubble bot-message">
                <div className="loading-message">
                  <div className="spinner"></div>
                  <span>Thinking...</span>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
      </div>
      
      {/* Practice Question Modal */}
      {showPracticeQuestion && (
        <div className="practice-modal">
          <div className="practice-modal-content">
            <h3 className="modal-title">Practice Question</h3>
            <p className="question-text">{showPracticeQuestion.question}</p>
            
            <div className="options-container">
              {showPracticeQuestion.options.map((option, index) => (
                <button
                  key={index}
                  onClick={() => handlePracticeAnswer(index)}
                  disabled={showAnswer}
                  className={`practice-option ${
                    showAnswer
                      ? index === showPracticeQuestion.correct
                        ? 'correct'
                        : selectedAnswer === index
                        ? 'incorrect'
                        : ''
                      : ''
                  }`}
                >
                  <div className="option-content">
                    {showAnswer && index === showPracticeQuestion.correct && (
                      <CheckCircle className="option-icon correct-icon" />
                    )}
                    {showAnswer && selectedAnswer === index && index !== showPracticeQuestion.correct && (
                      <XCircle className="option-icon incorrect-icon" />
                    )}
                    <span className="option-letter">{String.fromCharCode(65 + index)}.</span>
                    {option}
                  </div>
                </button>
              ))}
            </div>
            
            {showAnswer && (
              <div className="explanation">
                <p>
                  <strong>Explanation:</strong> {showPracticeQuestion.explanation}
                </p>
              </div>
            )}
            
            <button
              onClick={() => setShowPracticeQuestion(null)}
              className="close-button"
            >
              Close
            </button>
          </div>
        </div>
      )}
      
      {/* Quick Actions */}
      <div className="input-container">
        <div className="input-wrapper">
          <div className="quick-actions">
            {quickActions.map((action, index) => (
              <button
                key={index}
                onClick={action.action}
                className="quick-action-btn"
              >
                <action.icon className="action-icon" />
                <span>{action.text}</span>
              </button>
            ))}
          </div>
          
          {/* Input Area */}
          <div className="input-area">
            <div className="input-section">
              {selectedImage && (
                <div className="selected-image-container">
                  <img
                    src={selectedImage}
                    alt="Selected"
                    className="selected-image"
                  />
                  <button
                    onClick={() => setSelectedImage(null)}
                    className="remove-image"
                  >
                    ×
                  </button>
                </div>
              )}
              
              <div className="input-field-container">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                  placeholder="Ask about AWS services, CLI commands, troubleshooting, or request practice questions..."
                  className="chat-input"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="image-upload-btn"
                >
                  <Image className="upload-icon" />
                </button>
              </div>
              
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleImageUpload}
                style={{ display: 'none' }}
              />
            </div>
            
            <button
              onClick={handleSendMessage}
              disabled={isLoading || (!inputMessage.trim() && !selectedImage)}
              className="send-button"
            >
              <Send className="send-icon" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;