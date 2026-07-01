from jarvis.brain.controller import handle_command


def main():
    """Run the local CLI chat version of Jarvis."""
    print("Hello, Jarvis")
    print("Type a command, or type 'exit' to quit.")

    while True:
        user_command = input("You > ").strip()

        if user_command.lower() in ["exit", "quit"]:
            print("Jarvis > Goodbye.")
            break

        response = handle_command(user_command)
        print(f"Jarvis > {response}")


if __name__ == "__main__":
    main()
