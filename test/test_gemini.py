#!/usr/bin/env python3

import os
import json
import google.generativeai as genai

def test_gemini_json():
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("GEMINI_API_KEY not found")
        return
    
    client = genai.Client(api_key=api_key)
    
    # Test simple JSON generation
    prompt = 'Respond in JSON format: {"test": "hello"}'
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        
        text = response.candidates[0].content.parts[0].text
        print("Raw response:", text)
        
        # Handle Gemini's markdown code block format
        if text.startswith('```json'):
            # Extract JSON from markdown code blocks
            start = text.find('```json') + 7
            end = text.rfind('```')
            if end > start:
                text = text[start:end].strip()
        elif text.startswith('```'):
            # Handle generic code blocks
            start = text.find('```') + 3
            end = text.rfind('```')
            if end > start:
                text = text[start:end].strip()
        
        print("Extracted text:", text)
        
        # Try to parse as JSON
        try:
            parsed = json.loads(text)
            print("Successfully parsed JSON:", parsed)
        except json.JSONDecodeError as e:
            print("JSON parse error:", e)
            print("This might be why AI analysis is failing")
            
    except Exception as e:
        print("Gemini API error:", e)

if __name__ == "__main__":
    test_gemini_json() 