@app.route('/api/analyze_image', methods=['POST'])
def analyze_image():
    data = request.json
    image_data = data.get('image')
    text_prompt = data.get('text_prompt')
    input_msgs = [
        image_data,  # Send image as a single content block
        {'type': 'text', 'text': text_prompt}  # Separate user message
    ]
    response = process_image(input_msgs)
    return jsonify(response)
