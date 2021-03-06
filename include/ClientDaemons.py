import ClientData
import ClientImporting
import ClientThreading
import HydrusConstants as HC
import HydrusData
import HydrusExceptions
import HydrusGlobals as HG
import HydrusNATPunch
import HydrusPaths
import HydrusSerialisable
import HydrusThreading
import ClientConstants as CC
import random
import time
import wx

def DAEMONCheckExportFolders( controller ):
    
    if not controller.options[ 'pause_export_folders_sync' ]:
        
        HG.export_folders_running = True
        
        try:
            
            export_folder_names = controller.Read( 'serialisable_names', HydrusSerialisable.SERIALISABLE_TYPE_EXPORT_FOLDER )
            
            for name in export_folder_names:
                
                export_folder = controller.Read( 'serialisable_named', HydrusSerialisable.SERIALISABLE_TYPE_EXPORT_FOLDER, name )
                
                if controller.options[ 'pause_export_folders_sync' ] or HydrusThreading.IsThreadShuttingDown():
                    
                    break
                    
                
                export_folder.DoWork()
                
            
        finally:
            
            HG.export_folders_running = False
            
        
    
def DAEMONCheckImportFolders( controller ):
    
    if not controller.options[ 'pause_import_folders_sync' ]:
        
        HG.import_folders_running = True
        
        try:
            
            import_folder_names = controller.Read( 'serialisable_names', HydrusSerialisable.SERIALISABLE_TYPE_IMPORT_FOLDER )
            
            for name in import_folder_names:
                
                import_folder = controller.Read( 'serialisable_named', HydrusSerialisable.SERIALISABLE_TYPE_IMPORT_FOLDER, name )
                
                if controller.options[ 'pause_import_folders_sync' ] or HydrusThreading.IsThreadShuttingDown():
                    
                    break
                    
                
                import_folder.DoWork()
                
            
        finally:
            
            HG.import_folders_running = False
            
        
    
def DAEMONDownloadFiles( controller ):
    
    hashes = controller.Read( 'downloads' )
    
    num_downloads = len( hashes )
    
    if num_downloads > 0:
        
        client_files_manager = controller.client_files_manager
        
        successful_hashes = set()
        
        job_key = ClientThreading.JobKey()
        
        job_key.SetVariable( 'popup_text_1', 'initialising downloader' )
        
        controller.pub( 'message', job_key )
        
        for hash in hashes:
            
            job_key.SetVariable( 'popup_text_1', 'downloading ' + HydrusData.ConvertIntToPrettyString( num_downloads - len( successful_hashes ) ) + ' files from repositories' )
            
            ( media_result, ) = controller.Read( 'media_results', ( hash, ) )
            
            service_keys = list( media_result.GetLocationsManager().GetCurrent() )
            
            random.shuffle( service_keys )
            
            for service_key in service_keys:
                
                if service_key == CC.LOCAL_FILE_SERVICE_KEY: break
                elif service_key == CC.TRASH_SERVICE_KEY: continue
                
                try:
                    
                    service = controller.services_manager.GetService( service_key )
                    
                except:
                    
                    continue
                    
                
                if service.GetServiceType() == HC.FILE_REPOSITORY:
                    
                    file_repository = service
                    
                    if file_repository.IsFunctional():
                        
                        try:
                            
                            ( os_file_handle, temp_path ) = HydrusPaths.GetTempPath()
                            
                            try:
                                
                                file_repository.Request( HC.GET, 'file', { 'hash' : hash }, temp_path = temp_path )
                                
                                controller.WaitUntilModelFree()
                                
                                exclude_deleted = False # this is the important part here
                                allow_decompression_bombs = True
                                min_size = None
                                max_size = None
                                max_gif_size = None
                                min_resolution = None
                                max_resolution = None
                                automatic_archive = False
                                
                                file_import_options = ClientImporting.FileImportOptions()
                                
                                file_import_options.SetPreImportOptions( exclude_deleted, allow_decompression_bombs, min_size, max_size, max_gif_size, min_resolution, max_resolution )
                                file_import_options.SetPostImportOptions( automatic_archive )
                                
                                file_import_job = ClientImporting.FileImportJob( temp_path, file_import_options )
                                
                                client_files_manager.ImportFile( file_import_job )
                                
                                successful_hashes.add( hash )
                                
                                break
                                
                            finally:
                                
                                HydrusPaths.CleanUpTempPath( os_file_handle, temp_path )
                                
                            
                        except HydrusExceptions.ServerBusyException:
                            
                            job_key.SetVariable( 'popup_text_1', file_repository.GetName() + ' was busy. waiting 30s before trying again' )
                            
                            time.sleep( 30 )
                            
                            job_key.Delete()
                            
                            controller.pub( 'notify_new_downloads' )
                            
                            return
                            
                        except Exception as e:
                            
                            HydrusData.ShowText( 'Error downloading file!' )
                            HydrusData.ShowException( e )
                            
                        
                    
                elif service.GetServiceType() == HC.IPFS:
                    
                    multihashes = HG.client_controller.Read( 'service_filenames', service_key, { hash } )
                    
                    if len( multihashes ) > 0:
                        
                        multihash = multihashes[0]
                        
                        # this actually calls to a thread that can launch gui 'select from tree' stuff, so let's just break at this point
                        service.ImportFile( multihash )
                        
                        break
                        
                    
                
                if HydrusThreading.IsThreadShuttingDown():
                    
                    return
                    
                
            
        
        if len( successful_hashes ) > 0:
            
            job_key.SetVariable( 'popup_text_1', HydrusData.ConvertIntToPrettyString( len( successful_hashes ) ) + ' files downloaded' )
            
        
        job_key.Delete()
        
    
def DAEMONMaintainTrash( controller ):
    
    if HC.options[ 'trash_max_size' ] is not None:
        
        max_size = HC.options[ 'trash_max_size' ] * 1048576
        
        service_info = controller.Read( 'service_info', CC.TRASH_SERVICE_KEY )
        
        while service_info[ HC.SERVICE_INFO_TOTAL_SIZE ] > max_size:
            
            if HydrusThreading.IsThreadShuttingDown():
                
                return
                
            
            hashes = controller.Read( 'trash_hashes', limit = 10 )
            
            if len( hashes ) == 0:
                
                return
                
            
            content_update = HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_DELETE, hashes )
            
            service_keys_to_content_updates = { CC.TRASH_SERVICE_KEY : [ content_update ] }
            
            controller.WaitUntilModelFree()
            
            controller.WriteSynchronous( 'content_updates', service_keys_to_content_updates )
            
            service_info = controller.Read( 'service_info', CC.TRASH_SERVICE_KEY )
            
            time.sleep( 2 )
            
        
    
    if HC.options[ 'trash_max_age' ] is not None:
        
        max_age = HC.options[ 'trash_max_age' ] * 3600
        
        hashes = controller.Read( 'trash_hashes', limit = 10, minimum_age = max_age )
        
        while len( hashes ) > 0:
            
            if HydrusThreading.IsThreadShuttingDown():
                
                return
                
            
            content_update = HydrusData.ContentUpdate( HC.CONTENT_TYPE_FILES, HC.CONTENT_UPDATE_DELETE, hashes )
            
            service_keys_to_content_updates = { CC.TRASH_SERVICE_KEY : [ content_update ] }
            
            controller.WaitUntilModelFree()
            
            controller.WriteSynchronous( 'content_updates', service_keys_to_content_updates )
            
            hashes = controller.Read( 'trash_hashes', limit = 10, minimum_age = max_age )
            
            time.sleep( 2 )
            
        
    
def DAEMONSaveDirtyObjects( controller ):
    
    controller.SaveDirtyObjects()
    
def DAEMONSynchroniseAccounts( controller ):
    
    services = controller.services_manager.GetServices( HC.RESTRICTED_SERVICES )
    
    for service in services:
        
        if HydrusThreading.IsThreadShuttingDown():
            
            return
            
        
        service.SyncAccount()
        
    
def DAEMONSynchroniseRepositories( controller ):
    
    if not controller.options[ 'pause_repo_sync' ]:
        
        services = controller.services_manager.GetServices( HC.REPOSITORIES )
        
        for service in services:
            
            if HydrusThreading.IsThreadShuttingDown():
                
                return
                
            
            if controller.options[ 'pause_repo_sync' ]:
                
                return
                
            
            service.Sync( only_process_when_idle = True )
            
            if HydrusThreading.IsThreadShuttingDown():
                
                return
                
            
            time.sleep( 3 )
            
        
    

def DAEMONSynchroniseSubscriptions( controller ):
    
    subscription_names = list( controller.Read( 'serialisable_names', HydrusSerialisable.SERIALISABLE_TYPE_SUBSCRIPTION ) )
    
    if controller.new_options.GetBoolean( 'process_subs_in_random_order' ):
        
        random.shuffle( subscription_names )
        
    else:
        
        subscription_names.sort()
        
    
    HG.subscriptions_running = True
    
    try:
        
        for name in subscription_names:
            
            p1 = controller.options[ 'pause_subs_sync' ]
            p2 = HydrusThreading.IsThreadShuttingDown()
            
            if p1 or p2:
                
                return
                
            
            subscription = controller.Read( 'serialisable_named', HydrusSerialisable.SERIALISABLE_TYPE_SUBSCRIPTION, name )
            
            subscription.Sync()
            
        
    finally:
        
        HG.subscriptions_running = False
        
    
def DAEMONUPnP( controller ):
    
    try:
        
        local_ip = HydrusNATPunch.GetLocalIP()
        
        current_mappings = HydrusNATPunch.GetUPnPMappings()
        
        our_mappings = { ( internal_client, internal_port ) : external_port for ( description, internal_client, internal_port, external_ip_address, external_port, protocol, enabled ) in current_mappings }
        
    except:
        
        return # This IGD probably doesn't support UPnP, so don't spam the user with errors they can't fix!
        
    
    services = controller.services_manager.GetServices( ( HC.LOCAL_BOORU, ) )
    
    for service in services:
        
        internal_port = service.GetPort()
        
        if ( local_ip, internal_port ) in our_mappings:
            
            current_external_port = our_mappings[ ( local_ip, internal_port ) ]
            
            upnp_port = service.GetUPnPPort()
            
            if upnp_port is None or current_external_port != upnp_port:
                
                HydrusNATPunch.RemoveUPnPMapping( current_external_port, 'TCP' )
                
            
        
    
    for service in services:
        
        internal_port = service.GetPort()
        upnp_port = service.GetUPnPPort()
        
        if upnp_port is not None:
            
            if ( local_ip, internal_port ) not in our_mappings:
                
                service_type = service.GetServiceType()
                
                protocol = 'TCP'
                
                description = HC.service_string_lookup[ service_type ] + ' at ' + local_ip + ':' + str( internal_port )
                
                duration = 3600
                
                try:
                    
                    HydrusNATPunch.AddUPnPMapping( local_ip, internal_port, upnp_port, protocol, description, duration = duration )
                    
                except HydrusExceptions.FirewallException:
                    
                    HydrusData.Print( 'The UPnP Daemon tried to add ' + local_ip + ':' + internal_port + '->external:' + upnp_port + ' but it failed due to router error. Please try it manually to get a full log of what happened.' )
                    
                    return
                    
                except:
                    
                    raise
                    
                
            
        
    
