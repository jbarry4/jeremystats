# Loop 1: take one input and repeat it 10 times
text = input("Enter something to repeat: ")
for i in range(10):
    print(text)

# Loop 2: take the input inside the for loop (a new input each iteration)
for i in range(10):
    text = input(f"Enter value {i + 1}: ")
    print(text)
