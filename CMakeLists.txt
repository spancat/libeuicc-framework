cmake_minimum_required (VERSION 3.8)

project(libeuicc
        VERSION 2.0.1
        DESCRIPTION "libeuicc - eUICC Profile Manager Library"
	LANGUAGES C CXX OBJC)

set(FRAMEWORK_NAME "libeuicc")

enable_language(C)
enable_language(CXX)
enable_language(OBJC)

add_subdirectory(${CMAKE_SOURCE_DIR}/lpac/cjson ${CMAKE_BINARY_DIR}/cjson)
aux_source_directory(${CMAKE_CURRENT_SOURCE_DIR}/lpac/euicc LIB_EUICC_SRCS)

add_library(${FRAMEWORK_NAME} SHARED ${LIB_EUICC_SRCS} ${CMAKE_CURRENT_BINARY_DIR}/module.modulemap)

target_link_libraries(${FRAMEWORK_NAME} cjson-static)
target_include_directories(${FRAMEWORK_NAME} PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/..>)

# Install headers
file(GLOB ALL_HEADERS "lpac/euicc/*.h")

foreach(header ${ALL_HEADERS})
    if(${header} MATCHES "^.*\.private\.h$")
        list(REMOVE_ITEM ALL_HEADERS ${header})
    endif()
endforeach()

# Set the umbrella header path
set(UMBRELLA_HEADER_PATH ${CMAKE_CURRENT_BINARY_DIR}/libeuicc.h)

# Start writing the umbrella header file
file(WRITE ${UMBRELLA_HEADER_PATH} "#ifndef LIBEUICC_H\n#define LIBEUICC_H\n")

# Iterate over all headers and convert absolute paths to relative paths
foreach(header ${ALL_HEADERS})
    file(RELATIVE_PATH REL_HEADER ${CMAKE_CURRENT_SOURCE_DIR}/lpac/euicc ${header})
    file(APPEND ${UMBRELLA_HEADER_PATH} "#include \"${REL_HEADER}\"\n")
endforeach()

# Finish the umbrella header file
file(APPEND ${UMBRELLA_HEADER_PATH} "#endif /* LIBEUICC_H */\n")

# Add UMBRELLA_HEADER_PATH to ALL_HEADERS
list(APPEND ALL_HEADERS ${UMBRELLA_HEADER_PATH})

# Set modulemap property
set_property(SOURCE ${CMAKE_CURRENT_BINARY_DIR}/module.modulemap
  PROPERTY MACOSX_PACKAGE_LOCATION "Modules")
set(CMAKE_MACOSX_RPATH ON)

# Configure libeuicc iOS frmework
set(BUNDLE_RESOURCES
        ${CMAKE_CURRENT_SOURCE_DIR}/libeuicc-LICENSE
        ${CMAKE_CURRENT_SOURCE_DIR}/LICENSE
        ${CMAKE_CURRENT_BINARY_DIR}/libeuicc.pc)

target_sources(${FRAMEWORK_NAME} PRIVATE "${ALL_HEADERS}")
target_sources(${FRAMEWORK_NAME} PRIVATE "${BUNDLE_RESOURCES}")

set_target_properties(${FRAMEWORK_NAME} PROPERTIES
        FRAMEWORK TRUE
        FRAMEWORK_VERSION A
        MACOSX_FRAMEWORK_IDENTIFIER me.estk.libeuicc
        RESOURCE "${BUNDLE_RESOURCES}"
        VERSION ${PROJECT_VERSION}
        SOVERSION ${PROJECT_VERSION_MAJOR}
        PUBLIC_HEADER "${ALL_HEADERS}"
        RESOURCE "${BUNDLE_RESOURCES}"
        XCODE_ATTRIBUTE_CODE_SIGN_IDENTITY "iPhone Developer")

# Install a pkg-config file
configure_file(lpac/euicc/libeuicc.pc.in ${CMAKE_CURRENT_BINARY_DIR}/libeuicc.pc @ONLY)

# Configure a modulemap file
configure_file(module.modulemap.in ${CMAKE_CURRENT_BINARY_DIR}/module.modulemap @ONLY)

set_target_properties(${FRAMEWORK_NAME} PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/Frameworks
        ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/Frameworks
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/Frameworks)

install(TARGETS ${FRAMEWORK_NAME}
        FRAMEWORK DESTINATION Frameworks)
