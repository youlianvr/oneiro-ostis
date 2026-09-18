file(GLOB_RECURSE ONEIRO_MODULE_SOURCES CONFIGURE_DEPENDS
    "*.cpp" "*.hpp"
)

add_library(oneiro-module SHARED ${ONEIRO_MODULE_SOURCES})
target_link_libraries(oneiro-module
    LINK_PUBLIC sc-machine::sc-memory
    LINK_PUBLIC sc-machine::sc-agents-common
)
target_include_directories(oneiro-module
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}
)
set_target_properties(oneiro-module PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/extensions)

if(${SC_CLANG_FORMAT_CODE})
    target_clangformat_setup(oneiro-module)
endif()

if(${SC_BUILD_TESTS})
    add_subdirectory(oneiro-module/test)
endif()
