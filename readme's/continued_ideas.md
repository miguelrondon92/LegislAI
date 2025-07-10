-fix front end issue where legislative progress matches legislative history
-fix front end, some words need proper spacing in legislative history: Introreferral, Resolvingdifferences, Notused, Becamelaw
-Does congress API have API limits? If so, program those limits in to never surpass them. 


-Issue found in server log: 
INFO:werkzeug:127.0.0.1 - - [09/Jul/2025 22:53:24] "GET /bill/119/hr/1 HTTP/1.1" 200 -
INFO:werkzeug:127.0.0.1 - - [09/Jul/2025 22:53:24] "GET /static/css/style.css HTTP/1.1" 304 -
INFO:werkzeug:127.0.0.1 - - [09/Jul/2025 22:53:24] "GET /static/js/main.js HTTP/1.1" 304 -
ERROR:root:Congress API request failed: ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))
ERROR:root:Error calculating alignment: 'EnhancedAIAnalyzer' object has no attribute 'generate_user_specific_analysis'



In the future: 
    - Clients have the ability to chat with LegislAI about laws on the books, and legislation that is being proposed.  
    -set up govinfo API and create some sort of db that has current on the book laws. 
    -create a differ tool that shows what proposed bills would change what sections of laws. current law in red, proposed change in green. 
    -