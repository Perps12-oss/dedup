from dedup.ui.viewmodels.scan_page_vm import ScanPageViewModel


def test_scan_page_vm_sync():
    vm = ScanPageViewModel()
    seen = []
    vm.is_scanning.subscribe(lambda v: seen.append(v))
    vm.inner.is_scanning = True
    vm.sync_from_inner()
    assert True in seen
