import gradio as gr
from sidekick import Sidekick

async def setup():
    sidekick = Sidekick()
    await sidekick.setup()
    return sidekick

def free_resources(sidekick):
    """Used by gr.State.delete_callback, synchronous"""
    print ("cleaning up...")
    try:
        if sidekick:
            sidekick.cleanup()
    except Exception as e:
        print (f"Exception during clean up: {e}")

async def process_message(sidekick, message, success_criteria, history):
    results = await sidekick.run_superstep(message, success_criteria, history)
    return results
    # NOte: no longer reutnr results,sidekick as sidekick is the same and it will overwrite

async def reset(sidekick: Sidekick):
    # perform free_resource because we hold heavy objects, it is better to clean up right at the reset moment
    if sidekick:
        free_resources(sidekick)

    new_sidekick = Sidekick()
    await new_sidekick.setup()
    return "", "", [], new_sidekick
    #what happen to the previous sidekick?

with gr.Blocks() as ui:
    gr.Markdown("## Sidekick Personal Co-worker")
    sidekick_holder = gr.State(value=None, delete_callback=free_resources)
    with gr.Row():
        chatbot_textbox = gr.Chatbot(label="conversation", height=300)
    with gr.Group():
        with gr.Row():
            message_textbox = gr.Textbox(show_label=False, placeholder="Your request to the Sidekick")
        with gr.Row():
            success_criteria_textbox = gr.Textbox(
                show_label=False, placeholder="What are your success critiera?"
            )
    with gr.Row():
        reset_button = gr.Button("Reset", variant="stop")
        go_button = gr.Button("Go!", variant="primary")

    ui.load(setup, [], [sidekick_holder]) #sidekick_holder.value should hold sidekick object: setup(**[]) -> sidekick_holder.value

    for trigger in (message_textbox.submit,  success_criteria_textbox.submit, go_button.click):
        trigger(
            process_message, [sidekick_holder, message_textbox, success_criteria_textbox, chatbot_textbox], [chatbot_textbox]
        )

    reset_button.click(reset, [sidekick_holder], [message_textbox, success_criteria_textbox, chatbot_textbox, sidekick_holder])
    
    
ui.launch(theme="soft")