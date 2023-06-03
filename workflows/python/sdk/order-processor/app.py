import sys
import threading
from time import sleep
from dapr.ext.workflow import WorkflowRuntime
from workflow import order_processing_workflow, notify_activity, process_payment_activity, \
    verify_inventory_activity, update_inventory_activity, requst_approval_activity
from dapr.clients import DaprClient
from model import InventoryItem, OrderPayload
from util import get_address
from datetime import datetime

store_name = "statestore-actors"
workflow_component = "dapr"
workflow_name = "order_processing_workflow"
default_item_name = "cars"

class WorkflowConsoleApp:    
    def main(self):
        print("*** Welcome to the Dapr Workflow console app sample!")
        print("*** Using this app, you can place orders that start workflows.")
        # Wait for the sidecar to become available
        sleep(5)

        address = get_address()
        workflowRuntime = WorkflowRuntime(address["host"], address["port"])
        workflowRuntime.register_workflow(order_processing_workflow)
        workflowRuntime.register_activity(notify_activity)
        workflowRuntime.register_activity(requst_approval_activity)
        workflowRuntime.register_activity(verify_inventory_activity)
        workflowRuntime.register_activity(process_payment_activity)
        workflowRuntime.register_activity(update_inventory_activity)
        workflowRuntime.start()

        daprClient = DaprClient(address=f'{address["host"]}:{address["port"]}')
        baseInventory = {}
        baseInventory["paperclip"] = InventoryItem("Paperclip", 5, 100)
        baseInventory["cars"] = InventoryItem("Cars", 15000, 100)
        baseInventory["computers"] = InventoryItem("Computers", 500, 100)

        self.restock_inventory(daprClient, baseInventory)

        print("==========Begin the purchase of item:==========")        
        item_name = default_item_name
        order_quantity = 11

        total_cost = int(order_quantity) * baseInventory[item_name].per_item_cost
        order = OrderPayload(item_name=item_name, quantity=int(order_quantity), total_cost=total_cost)
        print(f'Starting order workflow, purchasing {order_quantity} of {item_name}')
        start_resp = daprClient.start_workflow(workflow_component=workflow_component,
                                               workflow_name=workflow_name,
                                               input=order)
        _id = start_resp.instance_id
        def prompt_for_approval(daprClient: DaprClient):
            daprClient.raise_workflow_event(instance_id=_id, workflow_component=workflow_component, 
                                            event_name="manager_approval", event_data={'approval': True})

        approval_seeked = False
        start_time = datetime.now()
        while True:
            time_delta = datetime.now() - start_time
            state = daprClient.get_workflow(instance_id=_id, workflow_component=workflow_component)
            if not state:
                print("Workflow not found!")  # not expected
            elif state.runtime_status == "Completed" or\
                    state.runtime_status == "Failed" or\
                    state.runtime_status == "Terminated":
                print(f'Workflow completed! Result: {state.runtime_status}')
                break
            if time_delta.total_seconds() >= 10:
                state = daprClient.get_workflow(instance_id=_id, workflow_component=workflow_component)
                if total_cost > 50000 and (
                    state.runtime_status != "Completed" or 
                    state.runtime_status != "Failed" or
                    state.runtime_status != "Terminated"
                    ) and not approval_seeked:
                    approval_seeked = True
                    threading.Thread(target=prompt_for_approval(daprClient), daemon=True).start()
            
        print("Purchase of item is ", state.runtime_status)

    def restock_inventory(self, daprClient: DaprClient, baseInventory):
        for key, item in baseInventory.items():
            print(f'item: {item}')
            item_str = f'{{"name": "{item.item_name}", "quantity": {item.quantity},\
                          "per_item_cost": {item.per_item_cost}}}'
            daprClient.save_state("statestore-actors", key, item_str)

if __name__ == '__main__':
    app = WorkflowConsoleApp()
    app.main()