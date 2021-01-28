import math

from lisa import TestCaseMetadata, TestSuite, TestSuiteMetadata
from lisa.operating_system import Windows
from lisa.testsuite import simple_requirement
from lisa.tools import Lscpu, Lsvmbus


class VmbusNames:
    def __init__(self, is_gen1: bool) -> None:
        self.names = [
            "Operating system shutdown",
            "Time Synchronization",
            "Heartbeat",
            "Data Exchange",
            "Synthetic mouse",
            "Synthetic keyboard",
            "Synthetic network adapter",
            "Synthetic SCSI Controller",
        ]
        if is_gen1:
            self.names.append("Synthetic IDE Controller")


@TestSuiteMetadata(
    area="core",
    category="functional",
    description="""
    This test suite uses to check correctness of vmbus channel
    """,
    tags=[],
)
class LsVmBus(TestSuite):
    @TestCaseMetadata(
        description="""
        This test is to check below vmbus names exist
            - Operating system shutdown
            - Time Synchronization
            - Heartbeat
            - Data Exchange
            - Synthetic mouse
            - Synthetic keyboard
            - Synthetic network adapter
            - Synthetic SCSI Controller
            - Synthetic IDE Controller (gen1 only)
        Check channel counts of each netvsc and storvsc SCSI device.
        Expected channel count of each netvsc is min (num of vcpu, 8).
        Expected channel count of each storvsc SCSI device is min (num of vcpu/4, 64).
        From the output of lsvmbus -vv command.
        """,
        priority=1,
        requirement=simple_requirement(unsupported_os=[Windows]),
    )
    def lsvmbus_channel_counting(self) -> None:
        node = self.environment.default_node
        # get vm generation info
        environment_information = node.get_node_information()
        # get expected vm bus names
        vmbus_class = VmbusNames(environment_information["vm_generation"] == "1")

        lsvmbus_tool = node.tools[Lsvmbus]
        vmbus_list = lsvmbus_tool.get_vmbuses()
        actual_vmbus_names = [x.vmbus_name for x in vmbus_list]
        for vmbus_name in vmbus_class.names:
            assert (
                vmbus_name in actual_vmbus_names
            ), f"expected vmbus_name '{vmbus_name}' doesn't exist."

        # get actual core count
        lscpu_tool = node.tools[Lscpu]
        core_count = lscpu_tool.get_core_count()
        # Each netvsc device should have "the_number_of_vCPUs" channel(s)
        # with a cap value of 8.
        expected_network_channel_count = min(core_count, 8)

        # Each storvsc SCSI device should have "the_number_of_vCPUs / 4" channel(s)
        # with a cap value of 64.
        expected_scsi_channel_count = math.ceil(min(core_count, 256) / 4)

        # When attach more than one nic
        # channels of each nic need follow the same logic
        for vmbus in vmbus_list:
            if vmbus.vmbus_name == "Synthetic network adapter":
                assert expected_network_channel_count == len(vmbus.channel_vp_map), (
                    f"actual network channel count '{len(vmbus.channel_vp_map)}'"
                    f" doesn't match expected channel count "
                    f"'{expected_network_channel_count}'"
                )
            if vmbus.vmbus_name == "Synthetic SCSI Controller":
                assert expected_scsi_channel_count == len(vmbus.channel_vp_map), (
                    f"actual scsi channel count '{len(vmbus.channel_vp_map)}'"
                    f" doesn't match expected channel count "
                    f"'{expected_scsi_channel_count}'"
                )
