import React, { useState, useRef, useEffect } from 'react';
import { post } from 'aws-amplify/api';
import './App.css';

function App() {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth'});
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    
    // Add user message to conversation (UI only)
    const userMessage = { role: 'user', content: input };
    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    
    const currentInput = input; // Store current input before clearing
    setInput('');
    setLoading(true);
    
    try {
      // Using Amplify v6 post method with .response
      const { body } = await post({
        apiName: 'bedrockRagAPI',
        path: '/rag',
        options: {
          body: { 
            query: currentInput  // Just send the text input
          }
        }
      }).response;
      
      // Parse the response data
      const responseData = await body.json();
      
      // Debug logging
      console.log('Full API response:', responseData);
      console.log('Citations received:', responseData.citations);

      // Add assistant response to conversation (UI only)
      if (responseData.text) {
        const assistantMessage = { 
          role: 'assistant', 
          content: responseData.text,
          citations: responseData.citations || [] // Store citations if available
        };
        setMessages([...updatedMessages, assistantMessage]);
      } else {
        // Fallback in case response format is different
        const assistantMessage = { 
          role: 'assistant', 
          content: 'Sorry, I received an unexpected response format.'
        };
        setMessages([...updatedMessages, assistantMessage]);
      }
    } catch (error) {
      console.error('Error calling API:', error);
      // Add error message to conversation (UI only)
      setMessages([
        ...updatedMessages, 
        { 
          role: 'assistant', 
          content: `Error: ${error.message}` 
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Function to render citations
  const renderCitations = (citations) => {    
    if (!citations || citations.length === 0) {
      console.log('No citations to render');
      return null;
    }
    
    return (
      <div className="citations-container">
        <h4>Citations:</h4>
        <ul className="citations-list">
          {citations.map((citation, index) => (
            <li key={index} className="citation-item">
              <span className="citation-text">{citation}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>AI Chat with Amazon Bedrock RAG</h1>
      </header>
      
      <div className="chat-container">
        <div className="conversation">
          {messages.length === 0 ? (
            <p className="empty-state">Start a conversation with Claude AI. I have knowledge base on JPMorgan Chase 2023 and 2024 shareholder reports.</p>
          ) : (
            messages.map((message, index) => (
              <div 
                key={index} 
                className={`message ${message.role === 'user' ? 'user-message' : 'assistant-message'}`}
              >
                <div className="message-role">{message.role === 'user' ? 'You' : 'Claude'}</div>
                <div className="message-content">
                  {message.content}
                  {message.role === 'assistant' && message.citations && renderCitations(message.citations)}
                </div>
              </div>
            ))
          )}
          {loading && (
            <div className="message assistant-message">
              <div className="message-role">Claude</div>
              <div className="message-content loading">Thinking...</div>
            </div>
          )}
          <div ref={messagesEndRef} /> {/* This element is used for auto-scrolling */}
        </div>
        
        <form onSubmit={handleSubmit} className="input-form">
          <div className="input-container">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message here..."
              rows={3}
              disabled={loading}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
            />
            <button type="submit" disabled={loading || !input.trim()}>
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default App;