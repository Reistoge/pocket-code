import os
import json
import argparse
import questionary
import tiktoken
from prompt_toolkit.key_binding import KeyBindings
from rich.live import Live
from rich.markdown import Markdown
from ollama import Client
from rich.console import Console

CONFIG_FILE = os.path.expanduser("~/.config/pocket-code/config.json")

SKIP_DIRS = {"venv", "__pycache__", "node_modules"}

def get_directory_files(directory="."):
    """Returns all files under directory as paths relative to it.

    Relative paths keep each context header meaningful (e.g. src/app/config.py)
    while still opening correctly from the current working directory.
    """
    found = []
    for root, dirs, files in os.walk(directory):
        # Skip hidden folders (.git, .venv, ...) and heavy dependency folders.
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
        found.extend(os.path.relpath(os.path.join(root, f), directory) for f in files)
    return sorted(found)

def count_tokens(text: str) -> int:
    """Estimates token count using tiktoken."""
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text, disallowed_special=()))

DEFAULT_PROFILES = {
    "coding": "You are a coding assistant. Keep answers concise and code-focused.",
    "general": "Keep answers concise, the answer can be of any topic or knowledge.",
}

def load_config():
    """Loads the config file, falling back to the default system instruction profiles."""
    config = {"profiles": DEFAULT_PROFILES}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config.update(json.load(f))
        except Exception as e:
            print(f"Warning: Could not read config, using defaults: {e}")
    if not isinstance(config.get("profiles"), dict) or not config["profiles"]:
        config["profiles"] = DEFAULT_PROFILES
    return config

def save_config(config):
    """Writes the config file, creating its directory if needed."""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save config: {e}")

def get_installed_models(client):
    """Fetches a list of installed models directly from Ollama."""
    try:
        response = client.list()
        return [model['model'] for model in response.get('models', [])]
    except Exception as e:
        Console().print(f"[red]Error connecting to Ollama to list models: {e}[/red]")
        return []

def main():
    parser = argparse.ArgumentParser(description="pocket-code: terminal coding chat for local Ollama models")
    parser.add_argument('--ask', action='store_true', help="Skip file selection and start in general knowledge mode")
    parser.add_argument('--change-model', action='store_true', help="Force prompt to change the selected model on startup")
    args = parser.parse_args()

    console = Console()
    client = Client(host='http://localhost:11434')
    model = None

    config = load_config()
    if not os.path.exists(CONFIG_FILE):
        # Create the file on first run so the profiles are easy to find and edit.
        save_config(config)
        console.print(f"[dim]Created config: {CONFIG_FILE}[/dim]")
    profiles = config["profiles"]
    profile = config.get("last_profile") or ("general" if args.ask else "coding")
    if profile not in profiles:
        profile = next(iter(profiles))

    try:
        # 1. Fetch available models dynamically
        installed_models = get_installed_models(client)
        if not installed_models:
            console.print("[red]No models found or Ollama is not running.[/red]")
            return

        selected_files = []
        # 2. Select files (Skip if --ask is passed)
        if not args.ask:
            files = get_directory_files()
            if not files:
                console.print("[red]No files found in the current directory.[/red]")
                return

            selected_files = questionary.checkbox(
                "Select files to include as context:",
                choices=files
            ).ask()

            if selected_files is None: # Handled Ctrl+C
                return

        # 3. Select model (Auto-load if saved, unless --change-model is passed)
        last_model = config.get("last_model")
        
        if last_model in installed_models and not args.change_model:
            model = last_model
            console.print(f"[dim]Auto-loaded model: {model} (use /models to switch)[/dim]")
        else:
            default_choice = last_model if last_model in installed_models else installed_models[0]
            model = questionary.select(
                "Select local model:",
                choices=installed_models,
                default=default_choice
            ).ask()

            if not model:
                 return 
            config["last_model"] = model
            save_config(config)

        # Read context
        context_data = ""
        if selected_files:
            for file in selected_files:
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        context_data += f"\n--- File: {file} ---\n{f.read()}\n"
                except Exception as e:
                    console.print(f"[red]Could not read {file}: {e}[/red]")

            # Token validation
            token_count = count_tokens(context_data)
            MAX_TOKENS = 8000
            BUFFER = 1000

            if token_count > MAX_TOKENS:
                console.print(f"\n[bold red]WARNING: Context ({token_count} tokens) exceeds {MAX_TOKENS}.[/bold red]")
            elif token_count > (MAX_TOKENS - BUFFER):
                console.print(f"\n[bold yellow]WARNING: Context ({token_count} tokens) is approaching {MAX_TOKENS}.[/bold yellow]")
            else:
                console.print(f"\n[green]Context size is safe: {token_count} tokens.[/green]")
            
            console.print(f"[green]Loaded {len(selected_files)} files into {model}.[/green]")
        else:
            console.print(f"[green]Starting general chat with {model}.[/green]")

        console.print(f"[dim]System instructions profile: {profile} (use /profile to switch)[/dim]")

        console.print("[cyan]Tip: Type '/' and press Tab for commands [/cyan]")
        console.print("[cyan]Tip: Press Ctrl+C while the model is typing to stop generation[/cyan]")

        chat_history = []
        commands = ["/files", "/models", "/profile", "/clear", "/view", "/ask ", "/exit"]

        # Setup Custom Keybindings for Multi-line Prompt
        bindings = KeyBindings()

        @bindings.add('enter')
        def _(event):
            # Enter submits the prompt
            event.current_buffer.validate_and_handle()
        
        @bindings.add('escape', 'enter') # Alt+Enter in terminal
        def _(event):
            # Alt+Enter adds a new line
            event.current_buffer.insert_text('\n')

        # 4. Prompt loop
        while True:
            try:
                # Adding multiline=True and custom keybindings
                prompt = questionary.autocomplete(
                    "\n>",
                    choices=commands,
                    style=questionary.Style([("prompt", "fg:cyan bold")]),
                    multiline=True,
                    key_bindings=bindings
                ).ask()
            except (KeyboardInterrupt, EOFError):
                break
                
            if prompt is None or prompt.strip().lower() in ['/exit', 'exit', 'bye']:
                break
            
            if not prompt.strip():
                continue

            # Command: Change Model
            if prompt.strip() == '/models':
                current_models = get_installed_models(client)
                if not current_models:
                    console.print("[red]No models found.[/red]")
                    continue

                new_model = questionary.select(
                    "Select local model:",
                    choices=current_models,
                    default=model if model in current_models else current_models[0]
                ).ask()

                if new_model and new_model != model:
                    console.print(f"[yellow]Unloading {model} to free VRAM...[/yellow]")
                    try:
                        client.generate(model=model, keep_alive=0)
                    except Exception as e:
                        console.print(f"[red]Could not unload old model: {e}[/red]")
                    
                    model = new_model
                    config["last_model"] = model
                    save_config(config)
                    console.print(f"[green]Switched to {model}.[/green]")
                continue

            # Command: Change System Instructions Profile
            if prompt.strip() == '/profile':
                new_profile = questionary.select(
                    "Select system instructions profile:",
                    choices=list(profiles),
                    default=profile
                ).ask()

                if new_profile and new_profile != profile:
                    profile = new_profile
                    config["last_profile"] = profile
                    save_config(config)
                    console.print(f"[green]Switched to profile: {profile}[/green]")
                continue

            # Command: Manage Files
            if prompt.strip() == '/files':
                all_files = get_directory_files()
                if not all_files:
                    console.print("[yellow]No files found in the current directory.[/yellow]")
                    continue

                # Pre-check currently selected files
                choices = [questionary.Choice(title=f, checked=(f in selected_files)) for f in all_files]

                new_selected_files = questionary.checkbox(
                    "Select files for the context (Space to toggle, Enter to confirm):",
                    choices=choices
                ).ask()

                if new_selected_files is not None:
                    selected_files = new_selected_files
                    context_data = ""
                    for file in selected_files:
                        try:
                            with open(file, 'r', encoding='utf-8') as f:
                                context_data += f"\n--- File: {file} ---\n{f.read()}\n"
                        except Exception as e:
                            console.print(f"[red]Could not read {file}: {e}[/red]")
                    
                    token_count = count_tokens(context_data)
                    console.print(f"[green]Context updated. Total files: {len(selected_files)}. New token count: {token_count}[/green]")
                continue

            # Command: View Context
            if prompt.strip() == '/view':
                if not context_data:
                    console.print("[yellow]No file context is currently loaded.[/yellow]")
                else:
                    console.print(f"[cyan]Loaded {len(selected_files)} files: {', '.join(selected_files)}\nToken count: {count_tokens(context_data)}[/cyan]")
                continue
                
            # Command: Clear Context
            if prompt.strip() == '/clear':
                context_data = ""
                selected_files = []
                chat_history = []
                console.print("[yellow]File context and conversation history cleared.[/yellow]")
                continue

            # Build the system instruction from the selected profile.
            # /ask answers from general knowledge and ignores the loaded file context.
            is_ask_command = prompt.startswith('/ask ')
            actual_prompt = prompt[5:].strip() if is_ask_command else prompt.strip()

            system_instruction = profiles[profile]
            if context_data and not is_ask_command:
                system_instruction += f"\n\nUse the following file context to answer the user's question.\nContext:\n{context_data}"

            # Build the message array including chat history
            messages = [{'role': 'system', 'content': system_instruction}]
            messages.extend(chat_history)
            messages.append({'role': 'user', 'content': actual_prompt})

            try:
                response = client.chat(
                    model=model,
                    messages=messages,
                    stream=True
                )
                
                console.print("\n[bold green]Response:[/bold green]")
                full_response = ""
                
                try:
                    with Live(console=console, refresh_per_second=15) as live:
                        for chunk in response:
                            content = chunk['message']['content']
                            full_response += content
                            live.update(Markdown(full_response))
                    print("\n")
                except KeyboardInterrupt:
                    # Catch Ctrl+C during generation
                    console.print("\n[yellow]Generation interrupted.[/yellow]\n")

                # Append to conversation history (even partial responses are useful context)
                chat_history.append({'role': 'user', 'content': actual_prompt})
                chat_history.append({'role': 'assistant', 'content': full_response})

            except Exception as e:
                console.print(f"[red]Error communicating with Ollama: {e}[/red]")

    finally:
        # VRAM Cleanup
        if model:
            console.print(f"\n[yellow]Unloading {model} from VRAM...[/yellow]")
            try:
                client.generate(model=model, keep_alive=0)
                console.print("[green]Model unloaded successfully. VRAM freed.[/green]")
            except Exception as e:
                console.print(f"[red]Failed to unload model: {e}[/red]")

if __name__ == "__main__":
    main()